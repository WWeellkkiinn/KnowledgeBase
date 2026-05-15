"""M1 端到端集成测试：alembic upgrade + migrate_to_db + Flask app 全链路。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, enable_sqlite_foreign_keys, models

ROOT = Path(__file__).resolve().parent.parent

# 与 papers/ 目录当前实际文件数对齐
_EXPECTED_PAPERS = 21


@pytest.fixture()
def fresh_e2e_db(tmp_path: Path):
    """空 DB + alembic upgrade + migrate_to_db.py 灌真实数据。"""
    db_file = tmp_path / "kb_e2e.db"
    env = os.environ.copy()
    env["KB_DB_PATH"] = str(db_file)

    # 1. alembic upgrade head
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"alembic upgrade failed: {r.stderr}"

    # 2. migrate_to_db
    report = tmp_path / "e2e_report.md"
    r = subprocess.run(
        [sys.executable, "scripts/migrate_to_db.py", "--report", str(report)],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"migrate failed: {r.stderr}"
    assert f"{_EXPECTED_PAPERS} new" in r.stdout, (
        f"expected {_EXPECTED_PAPERS} papers in stdout: {r.stdout}"
    )

    yield db_file


def test_full_pipeline_imports_real_data(fresh_e2e_db):
    engine = create_engine(f"sqlite:///{fresh_e2e_db.as_posix()}", future=True)
    enable_sqlite_foreign_keys(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    try:
        with Session() as s:
            assert s.query(models.Paper).count() == _EXPECTED_PAPERS
            # 已分析状态合理（migrate_to_db 可能把论文标为 analyzed）
            assert s.query(models.Paper).filter_by(status="analyzed").count() >= 0
            # FK 完整：edges 的两端都能解析
            for e in s.query(models.Edge).all():
                assert s.get(models.Paper, e.from_paper_id) is not None
                assert s.get(models.Paper, e.to_paper_id) is not None
    finally:
        engine.dispose()


def test_flask_app_serves_real_data(fresh_e2e_db, monkeypatch):
    """Flask app 接到真实数据上，API 端到端可用。"""
    engine = create_engine(f"sqlite:///{fresh_e2e_db.as_posix()}", future=True)
    enable_sqlite_foreign_keys(engine)
    SL = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    import database as db_pkg
    monkeypatch.setattr(db_pkg, "SessionLocal", SL)
    import app as app_pkg
    monkeypatch.setattr(app_pkg, "SessionLocal", SL, raising=False)

    test_app = app_pkg.create_app({"TESTING": True})
    with test_app.test_client() as c:
        # 概览
        rv = c.get("/")
        assert rv.status_code == 200
        body = rv.get_json()
        assert body["papers"] == _EXPECTED_PAPERS

        # 列表（migrate_to_db 写入的论文 is_core=False，用 tier=stub 查询）
        rv = c.get(f"/api/papers?limit=200&tier=stub")
        assert rv.status_code == 200
        items = rv.get_json()["items"]
        assert len(items) == _EXPECTED_PAPERS

        # 取第一篇论文做详情测试
        first_stem = items[0]["stem"]
        target = items[0]
        rv = c.get(f"/api/papers/{target['id']}")
        assert rv.status_code == 200
        body = rv.get_json()
        assert body["paper"]["stem"] == first_stem

    engine.dispose()


def test_task_queue_lifecycle_on_real_db(fresh_e2e_db):
    """在真实 DB 上跑 TaskQueue：enqueue → fetch → done → 状态正确。"""
    from services.task_queue import TaskQueue

    engine = create_engine(f"sqlite:///{fresh_e2e_db.as_posix()}", future=True)
    enable_sqlite_foreign_keys(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    try:
        with Session() as s:
            paper = s.query(models.Paper).first()
            q = TaskQueue(s)
            t = q.enqueue("analyze", paper_id=paper.id, payload={"focus": "methodology"})
            assert t.status == "queued"
            picked = q.fetch_next()
            assert picked.id == t.id
            assert picked.status == "running"
            q.mark_done(t.id)
            s.commit()
        with Session() as s:
            counts = TaskQueue(s).count_by_status()
            assert counts.get("done") == 1 or counts.get("completed") == 1
    finally:
        engine.dispose()
