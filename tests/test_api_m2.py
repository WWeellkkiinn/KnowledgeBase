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
                         doi="10.1/x", status="analyzed", source="root", is_core=True,
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
        "description": "machine learning papers",
        "active": True,
    })
    assert r.status_code == 201
    data = r.get_json()
    assert data["active"] is True
    assert data["description"] == "machine learning papers"
    assert "id" in data


def test_create_subscription_defaults(client):
    r = client.post("/api/subscriptions", json={})
    assert r.status_code == 201
    data = r.get_json()
    assert data["active"] is True


def test_list_subscriptions(client):
    client.post("/api/subscriptions", json={"description": "topic A", "active": True})
    client.post("/api/subscriptions", json={"description": "topic B", "active": False})
    r = client.get("/api/subscriptions")
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert len(items) == 2

    r2 = client.get("/api/subscriptions?active=1")
    assert len(r2.get_json()["items"]) == 1


def test_get_subscription(client):
    sid = client.post("/api/subscriptions", json={"description": "NLP"}).get_json()["id"]
    r = client.get(f"/api/subscriptions/{sid}")
    assert r.status_code == 200
    assert r.get_json()["description"] == "NLP"


def test_update_subscription_active(client):
    sid = client.post("/api/subscriptions", json={"description": "econ"}).get_json()["id"]
    r = client.patch(f"/api/subscriptions/{sid}", json={"active": False})
    assert r.status_code == 200
    assert r.get_json()["active"] is False


def test_update_subscription_description(client):  # noqa: secrets
    sid = client.post("/api/subscriptions", json={"description": "old topic"}).get_json()["id"]
    r = client.patch(f"/api/subscriptions/{sid}", json={"description": "new topic"})
    assert r.status_code == 200
    assert r.get_json()["description"] == "new topic"


def test_update_subscription_404(client):
    r = client.patch("/api/subscriptions/99999", json={"active": False})
    assert r.status_code == 404


def test_delete_subscription(client):
    sid = client.post("/api/subscriptions", json={"description": "to delete"}).get_json()["id"]
    r = client.delete(f"/api/subscriptions/{sid}")
    assert r.status_code == 204
    r2 = client.delete(f"/api/subscriptions/{sid}")
    assert r2.status_code == 404


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
