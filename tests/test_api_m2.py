"""M2.4 + M2.5 API 端到端：subscriptions CRUD / inbox / citations.bib。"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from database import Base, enable_sqlite_foreign_keys, models


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "kb_api_m2.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    SL = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with SL() as s:
        p = models.Paper(stem="seed", title="A Study", year=2020,
                         doi="10.1/x", status="analyzed", source="root",
                         authors_json=[{"family": "Smith", "given": "J"}])
        s.add(p); s.commit()

    import database as db_pkg
    monkeypatch.setattr(db_pkg, "SessionLocal", SL)
    import app as app_pkg
    monkeypatch.setattr(app_pkg, "SessionLocal", SL, raising=False)

    flask_app = app_pkg.create_app({"TESTING": True})
    with flask_app.test_client() as c:
        yield c
    engine.dispose()


# ─── subscriptions CRUD ─────────────────────────────────────────────


def test_create_subscription_returns_201(client):
    r = client.post("/api/subscriptions", json={
        "type": "paper_citations",
        "target": {"doi": "10.1/root"},
        "cron_expr": "every 7d",
    })
    assert r.status_code == 201
    data = r.get_json()
    assert data["type"] == "paper_citations"
    assert data["active"] is True


def test_create_subscription_400_on_bad_input(client):
    r = client.post("/api/subscriptions", json={"type": "bogus", "target": {}})
    assert r.status_code == 400


def test_list_subscriptions(client):
    client.post("/api/subscriptions", json={
        "type": "paper_citations", "target": {"doi": "10.1/a"},
        "cron_expr": "every 7d",
    })
    client.post("/api/subscriptions", json={
        "type": "topic_search", "target": {"query": "ABM"},
        "cron_expr": "every 1d", "active": False,
    })
    r = client.get("/api/subscriptions")
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert len(items) == 2

    r2 = client.get("/api/subscriptions?active=1")
    assert len(r2.get_json()["items"]) == 1


def test_update_subscription(client):
    sid = client.post("/api/subscriptions", json={
        "type": "paper_citations", "target": {"doi": "10.1/x"},
        "cron_expr": "every 7d",
    }).get_json()["id"]
    r = client.patch(f"/api/subscriptions/{sid}", json={"active": False})
    assert r.status_code == 200
    assert r.get_json()["active"] is False


def test_update_subscription_404(client):
    r = client.patch("/api/subscriptions/99999", json={"active": False})
    assert r.status_code == 404


def test_delete_subscription(client):
    sid = client.post("/api/subscriptions", json={
        "type": "paper_citations", "target": {"doi": "10.1/x"},
        "cron_expr": "every 7d",
    }).get_json()["id"]
    r = client.delete(f"/api/subscriptions/{sid}")
    assert r.status_code == 204
    r2 = client.delete(f"/api/subscriptions/{sid}")
    assert r2.status_code == 404


def test_delete_subscription_blocked_when_unread(client):
    """有未读 inbox 结果时，DELETE 应 409 要求 ?force=1 确认。"""
    sid = client.post("/api/subscriptions", json={
        "type": "paper_citations", "target": {"doi": "10.1/x"},
        "cron_expr": "every 7d",
    }).get_json()["id"]
    _seed_result(client, sid, doi="10.1/cite", notified=False)

    r = client.delete(f"/api/subscriptions/{sid}")
    assert r.status_code == 409

    r2 = client.delete(f"/api/subscriptions/{sid}?force=1")
    assert r2.status_code == 204


def test_create_subscription_rejects_oversize_target(client):
    """target_json 单值超过 1024 字符应被拒绝（DoS 防御）。"""
    r = client.post("/api/subscriptions", json={
        "type": "paper_citations",
        "target": {"doi": "10.1/x", "junk": "A" * 2000},
        "cron_expr": "every 7d",
    })
    assert r.status_code == 400


# ─── inbox ──────────────────────────────────────────────────────────


def _seed_result(client, sub_id, doi="10.1/c1", notified=False):
    # 直接通过 SessionLocal 注入 SubscriptionResult
    import app as app_pkg
    with app_pkg.SessionLocal() as s:
        s.add(models.SubscriptionResult(
            subscription_id=sub_id,
            paper_id=None,
            raw_metadata_json={"doi": doi, "title": "T"},
            notified=notified,
        ))
        s.commit()


def test_inbox_lists_results(client):
    sid = client.post("/api/subscriptions", json={
        "type": "paper_citations", "target": {"doi": "10.1/r"},
        "cron_expr": "every 7d",
    }).get_json()["id"]
    _seed_result(client, sid, doi="10.1/c1", notified=False)
    _seed_result(client, sid, doi="10.1/c2", notified=True)

    r = client.get("/api/inbox")
    assert len(r.get_json()["items"]) == 2

    r2 = client.get("/api/inbox?unread=1")
    items = r2.get_json()["items"]
    assert len(items) == 1
    assert items[0]["notified"] is False


def test_inbox_mark_read(client):
    sid = client.post("/api/subscriptions", json={
        "type": "paper_citations", "target": {"doi": "10.1/r"},
        "cron_expr": "every 7d",
    }).get_json()["id"]
    _seed_result(client, sid, doi="10.1/c1", notified=False)

    rid = client.get("/api/inbox").get_json()["items"][0]["id"]
    r = client.post(f"/api/inbox/{rid}/read")
    assert r.status_code == 200
    assert r.get_json()["notified"] is True


def test_inbox_mark_read_404(client):
    r = client.post("/api/inbox/99999/read")
    assert r.status_code == 404


# ─── citations / bibtex ─────────────────────────────────────────────


def test_generate_citation_for_paper(client):
    pid = client.get("/api/papers").get_json()["items"][0]["id"]
    r = client.post(f"/api/papers/{pid}/citation", json={})
    assert r.status_code == 200
    data = r.get_json()
    assert data["citation_key"] == "smith2020study"
    assert "Smith" in data["bibtex"]


def test_citation_404(client):
    r = client.post("/api/papers/99999/citation", json={})
    assert r.status_code == 404


def test_paper_bibtex_download(client):
    pid = client.get("/api/papers").get_json()["items"][0]["id"]
    r = client.get(f"/api/papers/{pid}/citations.bib")
    assert r.status_code == 200
    assert "application/x-bibtex" in r.headers["Content-Type"]
    assert b"@misc{smith2020study" in r.data or b"@article{smith2020study" in r.data
    # Content-Disposition 必须用清洗后的文件名（无 \r\n / 引号 / 路径分隔符）
    cd = r.headers["Content-Disposition"]
    assert "\r" not in cd and "\n" not in cd


def test_paper_bibtex_filename_sanitizes_dangerous_stem(client, tmp_path):
    """paper.stem 即使含 \\r\\n / 引号也不能逃逸 Content-Disposition header。"""
    import app as app_pkg
    with app_pkg.SessionLocal() as s:
        from database import models
        p = models.Paper(stem='evil\r\n"crlf', title="X", source="root",
                         status="analyzed", year=2020)
        s.add(p); s.commit()
        pid = p.id
        client.post(f"/api/papers/{pid}/citation", json={})

    r = client.get(f"/api/papers/{pid}/citations.bib")
    assert r.status_code == 200
    cd = r.headers["Content-Disposition"]
    assert "\r" not in cd and "\n" not in cd
    # `"` 被替换为下划线
    assert '"crlf' not in cd


def test_paper_bibtex_404(client):
    r = client.get("/api/papers/99999/citations.bib")
    assert r.status_code == 404


def test_all_citations_bibtex(client):
    pid = client.get("/api/papers").get_json()["items"][0]["id"]
    client.post(f"/api/papers/{pid}/citation", json={})
    r = client.get("/api/citations.bib")
    assert r.status_code == 200
    assert b"smith2020study" in r.data
