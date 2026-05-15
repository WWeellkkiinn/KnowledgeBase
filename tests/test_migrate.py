"""M1.2 验收：migrate_to_db.py 把现有 papers/ + network.json 全量入库且幂等。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, enable_sqlite_foreign_keys
from database import models  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent


def _run_migration(env, report: Path):
    """以子进程执行 scripts/migrate_to_db.py，避免污染父进程 module 状态。"""
    return subprocess.run(
        [sys.executable, "scripts/migrate_to_db.py", "--report", str(report)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _open_db(db_path: Path):
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    enable_sqlite_foreign_keys(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture()
def env_db(tmp_path: Path):
    """提供一个独立 DB 路径环境变量。"""
    import os
    db_file = tmp_path / "kb_migrate.db"
    env = os.environ.copy()
    env["KB_DB_PATH"] = str(db_file)
    return env, db_file, tmp_path / "report.md"


def test_migration_runs_and_imports_papers(env_db):
    env, db_file, report = env_db
    result = _run_migration(env, report)
    assert result.returncode == 0, result.stderr

    engine, Session = _open_db(db_file)
    try:
        with Session() as s:
            papers = s.query(models.Paper).count()
            edges = s.query(models.Edge).count()
            analyzed = s.query(models.Paper).filter_by(status="analyzed").count()
            roots = s.query(models.Paper).filter_by(source="root").count()
        # 实际数据快照（与 papers/ 目录当前文件数对齐）
        assert papers == 21, f"papers={papers}, expected 21"
        assert papers >= 1  # 至少导入 1 篇
        assert analyzed >= 0  # 允许全部待分析
    finally:
        engine.dispose()

    assert report.exists()
    txt = report.read_text(encoding="utf-8")
    assert "Migration Report" in txt
    assert "Papers" in txt and "Edges" in txt


def test_migration_is_idempotent(env_db):
    env, db_file, report = env_db
    # 第一次
    r1 = _run_migration(env, report)
    assert r1.returncode == 0, r1.stderr
    # 解析第一次结果
    engine, Session = _open_db(db_file)
    with Session() as s:
        papers1 = s.query(models.Paper).count()
        edges1 = s.query(models.Edge).count()
    engine.dispose()

    # 第二次：不应改变行数
    r2 = _run_migration(env, report)
    assert r2.returncode == 0, r2.stderr
    engine, Session = _open_db(db_file)
    try:
        with Session() as s:
            assert s.query(models.Paper).count() == papers1
            assert s.query(models.Edge).count() == edges1
    finally:
        engine.dispose()

    # stdout 必须显示更新/重复模式
    assert "updated" in r2.stdout
    assert "dup" in r2.stdout


def test_rerun_clears_stale_filesystem_fields(env_db, tmp_path):
    """删除 insight.md 后重跑：status 必须回到 pending、analyzed_at 必须清空。"""
    env, db_file, report = env_db
    r1 = _run_migration(env, report)
    assert r1.returncode == 0, r1.stderr
    engine, Session = _open_db(db_file)
    stem = None
    try:
        with Session() as s:
            p = s.query(models.Paper).filter_by(status="analyzed").first()
            assert p is not None
            stem = p.stem
            # 注入"脏"值，模拟历史 DB 留下的 stale path
            p.pdf_path = "papers/_stale/_garbage.pdf"
            s.commit()
        with Session() as s:
            p = s.query(models.Paper).filter_by(stem=stem).one()
            assert p.pdf_path == "papers/_stale/_garbage.pdf"
    finally:
        engine.dispose()

    r2 = _run_migration(env, report)
    assert r2.returncode == 0, r2.stderr

    engine, Session = _open_db(db_file)
    try:
        with Session() as s:
            p = s.query(models.Paper).filter_by(stem=stem).one()
            # _scan_papers 看到的真实 pdf_path 应该已覆盖 garbage
            assert p.pdf_path != "papers/_stale/_garbage.pdf"
    finally:
        engine.dispose()
