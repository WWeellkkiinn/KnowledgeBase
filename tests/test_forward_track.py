"""M2.1 验收：ForwardTrackService 双源去重 + 缓存 + API。"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from database import Base, enable_sqlite_foreign_keys, models
from services.forward_track_service import (
    ForwardTrackService,
    _CACHE_TTL,
    _normalize_doi,
    _utcnow,
)


@pytest.fixture()
def session(tmp_path: Path):
    db_file = tmp_path / "kb_ft.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


# ─── 归一化 ──────────────────────────────────────────────────────────


def test_normalize_doi_strips_prefix_and_lowercases():
    assert _normalize_doi("https://doi.org/10.1/AbC") == "10.1/abc"
    assert _normalize_doi("doi:10.1/X") == "10.1/x"
    assert _normalize_doi("  10.1/Y  ") == "10.1/y"
    assert _normalize_doi("") == ""


# ─── 合并去重 ────────────────────────────────────────────────────────


def test_merge_dedup_by_doi_marks_both():
    ss = [{"doi": "10.1/a", "title": "Short", "year": 2020, "authors": "", "source": "ss"}]
    oa = [{"doi": "10.1/A", "title": "Longer Title Here", "year": 2020,
           "authors": "X, Y", "source": "openalex"}]
    out = ForwardTrackService._merge(ss, oa)
    # 注意：合并键是入参原文（_fetch_* 已 _normalize_doi 过；此处用同一写法）
    # 此测试模拟两源已规整为小写后的输入
    norm_ss = [{**ss[0], "doi": "10.1/a"}]
    norm_oa = [{**oa[0], "doi": "10.1/a"}]
    out = ForwardTrackService._merge(norm_ss, norm_oa)
    assert len(out) == 1
    assert out[0]["source"] == "both"
    assert out[0]["title"] == "Longer Title Here"  # 择长
    assert out[0]["authors"] == "X, Y"  # 择非空


def test_merge_dedup_by_titleyear_when_no_doi():
    ss = [{"doi": "", "title": "Same Title", "year": 2021, "authors": "", "source": "ss"}]
    oa = [{"doi": "", "title": "same title", "year": 2021,
           "authors": "Z", "source": "openalex"}]
    out = ForwardTrackService._merge(ss, oa)
    assert len(out) == 1
    assert out[0]["source"] == "both"


def test_merge_keeps_distinct_by_doi():
    out = ForwardTrackService._merge(
        [{"doi": "10.1/a", "title": "A", "year": 2020, "authors": "", "source": "ss"}],
        [{"doi": "10.1/b", "title": "B", "year": 2021, "authors": "", "source": "openalex"}],
    )
    assert {r["doi"] for r in out} == {"10.1/a", "10.1/b"}


def test_merge_drops_no_doi_no_title():
    out = ForwardTrackService._merge(
        [{"doi": "", "title": "", "year": None, "authors": "", "source": "ss"}],
    )
    assert out == []


# ─── HTTP 数据源（mock httpx）───────────────────────────────────────


class _FakeResp:
    def __init__(self, status: int, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def test_fetch_ss_parses_citing_papers(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        assert "/paper/DOI:10.1/abc/citations" in url
        return _FakeResp(200, {
            "data": [
                {"citingPaper": {
                    "title": "A cites X",
                    "year": 2024,
                    "authors": [{"name": "Alice"}, {"name": "Bob"}],
                    "externalIds": {"DOI": "10.1/CITE1"},
                }},
                {"citingPaper": {
                    "title": "B cites X",
                    "year": 2023,
                    "authors": [],
                    "externalIds": {},
                }},
            ]
        })

    monkeypatch.setattr(httpx, "get", fake_get)
    svc = ForwardTrackService()
    out = svc._fetch_ss("10.1/abc", limit=100)
    assert len(out) == 2
    assert out[0]["doi"] == "10.1/cite1"
    assert out[0]["authors"] == "Alice, Bob"
    assert out[1]["doi"] == ""


def test_fetch_ss_returns_empty_on_http_error(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeResp(429, {}))
    assert ForwardTrackService()._fetch_ss("10.1/x", 100) == []


def test_fetch_openalex_resolves_work_id_then_lists_citing(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        if "/works/doi:" in url:
            return _FakeResp(200, {"id": "https://openalex.org/W12345"})
        if url.endswith("/works"):
            assert params["filter"] == "cites:W12345"
            return _FakeResp(200, {"results": [{
                "title": "C cites X",
                "doi": "https://doi.org/10.1/CITE2",
                "publication_year": 2025,
                "authorships": [{"author": {"display_name": "Carol"}}],
            }]})
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(httpx, "get", fake_get)
    out = ForwardTrackService()._fetch_openalex("10.1/abc", 100)
    assert len(out) == 1
    assert out[0]["doi"] == "10.1/cite2"
    assert out[0]["authors"] == "Carol"
    assert len(calls) == 2


def test_fetch_openalex_no_work_id_returns_empty(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeResp(404, {}))
    assert ForwardTrackService()._fetch_openalex("10.1/x", 100) == []


# ─── 主入口 + 缓存 ─────────────────────────────────────────────────


def test_track_writes_cache_and_second_call_hits_cache(session, monkeypatch):
    n_calls = {"n": 0}

    def fake_fetch_ss(self, doi, limit):
        n_calls["n"] += 1
        return [{"doi": "10.1/cite1", "title": "T", "year": 2024,
                 "authors": "A", "source": "ss"}]

    def fake_fetch_oa(self, doi, limit):
        return []

    monkeypatch.setattr(ForwardTrackService, "_fetch_ss", fake_fetch_ss)
    monkeypatch.setattr(ForwardTrackService, "_fetch_openalex", fake_fetch_oa)

    svc = ForwardTrackService(db_session=session)
    r1 = svc.track("10.1/ROOT")
    assert r1["cached"] is False
    assert r1["citing_count"] == 1
    assert r1["doi"] == "10.1/root"

    # 第二次：命中缓存，不调上游
    r2 = svc.track("10.1/root")
    assert r2["cached"] is True
    assert n_calls["n"] == 1

    # 缓存表里应有一行
    rows = session.execute(select(models.ForwardTrackCache)).scalars().all()
    assert len(rows) == 1
    assert rows[0].doi == "10.1/root"


def test_track_refresh_true_bypasses_cache(session, monkeypatch):
    n_calls = {"n": 0}

    def fake_fetch_ss(self, doi, limit):
        n_calls["n"] += 1
        return [{"doi": f"10.1/c{n_calls['n']}", "title": "T", "year": 2024,
                 "authors": "", "source": "ss"}]

    monkeypatch.setattr(ForwardTrackService, "_fetch_ss", fake_fetch_ss)
    monkeypatch.setattr(ForwardTrackService, "_fetch_openalex",
                        lambda *a, **kw: [])

    svc = ForwardTrackService(db_session=session)
    svc.track("10.1/root")
    svc.track("10.1/root", refresh=True)
    assert n_calls["n"] == 2


def test_track_cache_expired_refetches(session, monkeypatch):
    monkeypatch.setattr(ForwardTrackService, "_fetch_ss",
                        lambda *a, **kw: [{"doi": "10.1/c", "title": "T",
                                            "year": 2024, "authors": "",
                                            "source": "ss"}])
    monkeypatch.setattr(ForwardTrackService, "_fetch_openalex",
                        lambda *a, **kw: [])

    svc = ForwardTrackService(db_session=session)
    svc.track("10.1/root")
    # 把缓存时间往前推超出 TTL
    row = session.execute(select(models.ForwardTrackCache)).scalar_one()
    row.fetched_at = _utcnow() - _CACHE_TTL - timedelta(minutes=1)
    session.flush()

    r = svc.track("10.1/root")
    assert r["cached"] is False  # 过期重查


def test_track_rejects_empty_doi(session):
    svc = ForwardTrackService(db_session=session)
    with pytest.raises(ValueError, match="doi is required"):
        svc.track("")


def test_track_cache_at_exact_ttl_treated_as_expired(session, monkeypatch):
    """TTL 边界：fetched_at 刚好等于 7 天前（含早一微秒）当作过期重查（>= 比较）。"""
    monkeypatch.setattr(ForwardTrackService, "_fetch_ss",
                        lambda *a, **kw: [{"doi": "10.1/c", "title": "T",
                                            "year": 2024, "authors": "",
                                            "source": "ss"}])
    monkeypatch.setattr(ForwardTrackService, "_fetch_openalex",
                        lambda *a, **kw: [])

    svc = ForwardTrackService(db_session=session)
    svc.track("10.1/root")
    row = session.execute(select(models.ForwardTrackCache)).scalar_one()
    row.fetched_at = _utcnow() - _CACHE_TTL
    session.flush()
    r = svc.track("10.1/root")
    assert r["cached"] is False  # >= TTL → 重查


def test_track_cache_race_uses_update_path(session, monkeypatch):
    """并发同 DOI miss 时第二个 INSERT 撞 UNIQUE，应回退到 UPDATE 并返回结果。"""
    monkeypatch.setattr(ForwardTrackService, "_fetch_ss",
                        lambda *a, **kw: [])
    monkeypatch.setattr(ForwardTrackService, "_fetch_openalex",
                        lambda *a, **kw: [])

    svc = ForwardTrackService(db_session=session)
    # 模拟"另一线程已写入" —— 直接预先种入一行
    session.add(models.ForwardTrackCache(
        doi="10.1/root", result_json={"prior": True}, fetched_at=_utcnow(),
    ))
    session.commit()
    # 现在再 track，refresh=True 强制走 fetch + write_cache 路径
    r = svc.track("10.1/root", refresh=True)
    # 应该完成（UPDATE 路径）而不是抛 IntegrityError
    assert r["doi"] == "10.1/root"
    rows = session.execute(select(models.ForwardTrackCache)).scalars().all()
    assert len(rows) == 1
    assert "prior" not in rows[0].result_json  # 已覆盖


# ─── API ─────────────────────────────────────────────────────────────


@pytest.fixture()
def api_setup(tmp_path: Path, monkeypatch):
    """临时 DB + 替换 SessionLocal + 注入上游 mock，返回 (client, seed_paper_id)。"""
    db_file = tmp_path / "kb_api.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    SL = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with SL() as s:
        p = models.Paper(stem="root_2024", doi="10.1/ROOT",
                         status="analyzed", source="root", title="Root")
        p2 = models.Paper(stem="no_doi", doi=None,
                          status="pending", source="ref", title="NoDOI")
        s.add_all([p, p2])
        s.commit()
        ids = {"root": p.id, "no_doi": p2.id}

    import database as db_pkg
    monkeypatch.setattr(db_pkg, "SessionLocal", SL)
    import app as app_pkg
    monkeypatch.setattr(app_pkg, "SessionLocal", SL, raising=False)

    from services import forward_track_service as fts_mod
    monkeypatch.setattr(fts_mod.ForwardTrackService, "_fetch_ss",
                        lambda self, d, l: [{"doi": "10.1/c", "title": "T",
                                              "year": 2024, "authors": "",
                                              "source": "ss"}])
    monkeypatch.setattr(fts_mod.ForwardTrackService, "_fetch_openalex",
                        lambda self, d, l: [])

    test_app = app_pkg.create_app({"TESTING": True})
    with test_app.test_client() as c:
        yield c, ids
    engine.dispose()


def test_api_forward_track_404_when_paper_missing(api_setup):
    client, _ = api_setup
    resp = client.post("/api/papers/9999/forward-track", json={})
    assert resp.status_code == 404


def test_api_forward_track_422_when_no_doi(api_setup):
    client, ids = api_setup
    resp = client.post(f"/api/papers/{ids['no_doi']}/forward-track", json={})
    assert resp.status_code == 422


def test_api_forward_track_returns_payload_and_caches(api_setup):
    client, ids = api_setup
    r1 = client.post(f"/api/papers/{ids['root']}/forward-track", json={})
    assert r1.status_code == 200
    body1 = r1.get_json()
    assert body1["cached"] is False
    assert body1["citing_count"] == 1
    assert body1["doi"] == "10.1/root"

    r2 = client.post(f"/api/papers/{ids['root']}/forward-track", json={})
    assert r2.get_json()["cached"] is True


def test_api_forward_track_invalid_limit(api_setup):
    client, ids = api_setup
    resp = client.post(f"/api/papers/{ids['root']}/forward-track",
                       json={"limit": "abc"})
    assert resp.status_code == 400
