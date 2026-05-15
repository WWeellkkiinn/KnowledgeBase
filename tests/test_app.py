"""M1.5 验收：Flask app 起得来、API 返回 JSON、绑定 DB 正常。"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, enable_sqlite_foreign_keys, models


@pytest.fixture()
def app_client(tmp_path: Path, monkeypatch):
    """临时 DB + monkeypatch 全局 SessionLocal；不依赖 importlib.reload。"""
    db_file = tmp_path / "kb_app.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    SL = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    # 种数据
    with SL() as s:
        p = models.Paper(stem="seed_2024", title="Seed", source="root", status="analyzed", is_core=True)
        s.add(p); s.flush()
        s.add(models.Task(type="analyze", paper_id=p.id))
        s.commit()

    # 让 app 使用临时 SessionLocal
    import database as db_pkg
    monkeypatch.setattr(db_pkg, "SessionLocal", SL)
    import app as app_pkg
    monkeypatch.setattr(app_pkg, "SessionLocal", SL, raising=False)

    test_app = app_pkg.create_app({"TESTING": True})
    with test_app.test_client() as c:
        yield c
    engine.dispose()


def test_health(app_client):
    rv = app_client.get("/api/health")
    assert rv.status_code == 200
    assert rv.get_json() == {"status": "ok"}


def test_index_returns_counts(app_client):
    rv = app_client.get("/")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["papers"] == 1
    assert data["service"] == "KnowledgeBase"


def test_list_papers(app_client):
    rv = app_client.get("/api/papers")
    assert rv.status_code == 200
    data = rv.get_json()
    assert len(data["items"]) == 1
    assert data["items"][0]["stem"] == "seed_2024"


def test_filter_papers_by_status(app_client):
    rv = app_client.get("/api/papers?status=pending")
    assert rv.status_code == 200
    assert rv.get_json()["items"] == []


def test_get_paper_with_edges(app_client):
    list_rv = app_client.get("/api/papers")
    pid = list_rv.get_json()["items"][0]["id"]
    rv = app_client.get(f"/api/papers/{pid}")
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["paper"]["stem"] == "seed_2024"
    assert body["edges_in"] == []
    assert body["edges_out"] == []


def test_get_paper_not_found(app_client):
    rv = app_client.get("/api/papers/99999")
    assert rv.status_code == 404


def test_list_tasks(app_client):
    rv = app_client.get("/api/tasks")
    assert rv.status_code == 200
    items = rv.get_json()["items"]
    assert len(items) == 1
    assert items[0]["type"] == "analyze"
    assert items[0]["status"] == "queued"
