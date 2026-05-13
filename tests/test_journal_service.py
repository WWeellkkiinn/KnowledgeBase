"""M2.2 验收：JournalService seed 引导、查询、OpenAlex 兜底、attach_to_paper。"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from database import Base, enable_sqlite_foreign_keys, models
from services.journal_service import (
    JournalService,
    SEED_PATH,
    _normalize_issn,
    _normalize_name,
)


@pytest.fixture()
def session(tmp_path: Path):
    db_file = tmp_path / "kb_journal.db"
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


def test_normalize_issn_strips_whitespace():
    assert _normalize_issn(" 0002-8282 ") == "0002-8282"
    assert _normalize_issn("") == ""


def test_normalize_issn_uppercases_x_checksum():
    """ISSN X 校验位的大小写应统一为大写，避免去重失败。"""
    assert _normalize_issn("0305-750x") == "0305-750X"
    assert _normalize_issn("0305-750X") == "0305-750X"


def test_bootstrap_handles_malformed_json(session, tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("not json {", encoding="utf-8")
    assert JournalService().bootstrap_from_seed(session, seed_path=bad) == \
        {"inserted": 0, "updated": 0, "skipped": 0}


def test_bootstrap_handles_non_list_root(session, tmp_path):
    bad = tmp_path / "obj.json"
    bad.write_text('{"not": "a list"}', encoding="utf-8")
    assert JournalService().bootstrap_from_seed(session, seed_path=bad) == \
        {"inserted": 0, "updated": 0, "skipped": 0}


def test_bootstrap_handles_illegal_tier_and_types(session, tmp_path):
    """非法 tier / 错误类型字段应被规整为 None，不阻塞合法行。"""
    import json as _json
    bad = tmp_path / "mixed.json"
    bad.write_text(_json.dumps([
        "not-a-dict",
        {"issn": "1234-5678", "name": "Valid", "quality_tier": 99},  # 非法 tier
        {"issn": "1234-5679", "name": "Also Valid",
         "quality_tier": 2, "publisher": 12345},  # 非法 publisher 类型
    ]), encoding="utf-8")
    r = JournalService().bootstrap_from_seed(session, seed_path=bad)
    assert r["inserted"] == 2 and r["skipped"] == 1
    valid = JournalService.lookup_by_issn(session, "1234-5678")
    assert valid is not None
    assert valid.quality_tier is None  # 非法 tier → None


def test_normalize_name_lowercase_and_compact():
    assert _normalize_name("  Management  Science.  ") == "management science"
    assert _normalize_name("Journal of Economic Behavior & Organization") == \
        "journal of economic behavior organization"


# ─── seed 文件本身 ──────────────────────────────────────────────────


def test_seed_file_exists_and_well_formed():
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) >= 20
    for row in data:
        assert "issn" in row and "name" in row
        assert row.get("quality_tier") in (1, 2, 3, 4, None)


# ─── bootstrap_from_seed ────────────────────────────────────────────


def test_bootstrap_inserts_journals(session):
    result = JournalService().bootstrap_from_seed(session)
    assert result["inserted"] >= 20
    assert result["updated"] == 0

    rows = session.execute(select(models.Journal)).scalars().all()
    issns = {r.issn for r in rows}
    assert "0025-1909" in issns  # Management Science


def test_bootstrap_is_idempotent_updates_on_rerun(session):
    svc = JournalService()
    r1 = svc.bootstrap_from_seed(session)
    r2 = svc.bootstrap_from_seed(session)
    assert r2["inserted"] == 0
    assert r2["updated"] == r1["inserted"]


def test_bootstrap_handles_missing_file(session, tmp_path):
    fake = tmp_path / "nope.json"
    r = JournalService().bootstrap_from_seed(session, seed_path=fake)
    assert r == {"inserted": 0, "updated": 0, "skipped": 0}


def test_bootstrap_skips_invalid_rows(session, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([
        {"issn": "", "name": "No ISSN"},
        {"issn": "1234-5678", "name": ""},
        {"issn": "9999-9999", "name": "Good", "quality_tier": 2},
    ]), encoding="utf-8")
    r = JournalService().bootstrap_from_seed(session, seed_path=bad)
    assert r == {"inserted": 1, "updated": 0, "skipped": 2}


# ─── lookup ─────────────────────────────────────────────────────────


def test_lookup_by_issn(session):
    JournalService().bootstrap_from_seed(session)
    j = JournalService.lookup_by_issn(session, "0025-1909")
    assert j is not None
    assert j.name == "Management Science"


def test_lookup_by_issn_empty_returns_none(session):
    assert JournalService.lookup_by_issn(session, "") is None


def test_lookup_by_name_normalizes(session):
    JournalService().bootstrap_from_seed(session)
    j = JournalService.lookup_by_name(session, "MANAGEMENT SCIENCE")
    assert j is not None
    assert j.issn == "0025-1909"


# ─── OpenAlex 兜底 ──────────────────────────────────────────────────


class _FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def test_fetch_journal_from_doi_parses_primary_location(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return _FakeResp(200, {
            "primary_location": {"source": {
                "display_name": "Some Journal",
                "issn_l": "1111-2222",
                "issn": ["1111-2222", "3333-4444"],
                "host_organization_name": "Some Publisher",
            }},
            "open_access": {"oa_status": "gold"},
        })

    monkeypatch.setattr(httpx, "get", fake_get)
    meta = JournalService().fetch_journal_from_doi("10.1/x")
    assert meta == {
        "issn": "1111-2222",
        "name": "Some Journal",
        "publisher": "Some Publisher",
        "oa_status": "gold",
        "source_dataset": "openalex",
    }


def test_fetch_journal_from_doi_falls_back_to_issn_array(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return _FakeResp(200, {
            "primary_location": {"source": {
                "display_name": "X",
                "issn": ["aaaa-bbbb"],
            }},
        })

    monkeypatch.setattr(httpx, "get", fake_get)
    meta = JournalService().fetch_journal_from_doi("10.1/x")
    assert meta["issn"] == "aaaa-bbbb"


def test_fetch_journal_returns_none_on_http_error(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeResp(404, {}))
    assert JournalService().fetch_journal_from_doi("10.1/x") is None


def test_fetch_journal_returns_none_on_empty_doi():
    assert JournalService().fetch_journal_from_doi("") is None


# ─── attach_to_paper ────────────────────────────────────────────────


def test_attach_links_existing_journal_via_issn(session):
    svc = JournalService()
    svc.bootstrap_from_seed(session)
    p = models.Paper(stem="x", doi="10.1/x", status="pending", source="root")
    session.add(p); session.flush()

    journal = svc.attach_to_paper(session, p, meta={
        "issn": "0025-1909", "name": "Management Science",
        "publisher": "INFORMS", "source_dataset": "openalex",
    })
    assert journal is not None
    assert journal.issn == "0025-1909"
    assert p.journal_id == journal.id
    # seed 已设的 Tier 不应被 OpenAlex 覆盖
    assert journal.quality_tier == 1


def test_attach_creates_new_journal_when_unknown(session):
    p = models.Paper(stem="x", doi="10.1/x", status="pending", source="root")
    session.add(p); session.flush()
    j = JournalService().attach_to_paper(session, p, meta={
        "issn": "9999-0001", "name": "New Journal",
        "source_dataset": "openalex",
    })
    assert j is not None
    assert j.quality_tier is None  # 新建无 tier
    assert p.journal_id == j.id


def test_attach_handles_meta_without_issn(session):
    p = models.Paper(stem="x", doi="10.1/x", status="pending", source="root")
    session.add(p); session.flush()
    j = JournalService().attach_to_paper(session, p, meta={
        "issn": "", "name": "Anon Journal",
        "source_dataset": "openalex",
    })
    assert j is not None
    assert j.issn.startswith("u:")  # surrogate
    assert p.journal_id == j.id


def test_attach_returns_none_when_no_meta(session, monkeypatch):
    p = models.Paper(stem="x", doi="10.1/x", status="pending", source="root")
    session.add(p); session.flush()
    monkeypatch.setattr(JournalService, "fetch_journal_from_doi",
                        lambda self, d: None)
    assert JournalService().attach_to_paper(session, p) is None
    assert p.journal_id is None


def test_attach_via_doi_calls_openalex(session, monkeypatch):
    """meta=None 时应触发 OpenAlex 拉取并 attach。"""
    p = models.Paper(stem="x", doi="10.1/x", status="pending", source="root")
    session.add(p); session.flush()

    monkeypatch.setattr(JournalService, "fetch_journal_from_doi",
                        lambda self, doi: {
                            "issn": "1111-9999", "name": "Hit",
                            "publisher": "P", "oa_status": "green",
                            "source_dataset": "openalex",
                        })
    j = JournalService().attach_to_paper(session, p)
    assert j is not None
    assert j.oa_status == "green"
    assert p.journal_id == j.id
