"""M1.4 验收：TaskQueue 行为正确——FIFO、重试、崩溃恢复。"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, enable_sqlite_foreign_keys
from database import models  # noqa: F401
from services.task_queue import TaskQueue


@pytest.fixture()
def session(tmp_path: Path):
    db_file = tmp_path / "tq.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with Session() as s:
        yield s
    engine.dispose()


def test_enqueue_and_fetch_fifo(session):
    q = TaskQueue(session)
    a = q.enqueue("analyze", payload={"x": 1})
    b = q.enqueue("analyze", payload={"x": 2})
    first = q.fetch_next()
    assert first.id == a.id
    assert first.status == "running"
    assert first.attempt == 1
    second = q.fetch_next()
    assert second.id == b.id


def test_fetch_filtered_by_type(session):
    q = TaskQueue(session)
    q.enqueue("analyze")
    q.enqueue("forward_track")
    t = q.fetch_next(type="forward_track")
    assert t.type == "forward_track"


def test_mark_done(session):
    q = TaskQueue(session)
    t = q.enqueue("analyze")
    q.fetch_next()
    q.mark_done(t.id)
    session.refresh(t)
    assert t.status == "completed"
    assert t.finished_at is not None


def test_mark_failed_retries_then_fails(session):
    q = TaskQueue(session)
    t = q.enqueue("analyze", max_attempts=2)

    # attempt 1
    q.fetch_next()
    q.mark_failed(t.id, "boom")
    session.refresh(t)
    assert t.status == "queued"      # 还有重试机会
    assert t.attempt == 1
    assert "[attempt 1] boom" in t.error_log

    # attempt 2 (达到上限)
    q.fetch_next()
    q.mark_failed(t.id, "boom again")
    session.refresh(t)
    assert t.status == "failed"
    assert t.attempt == 2


def test_reset_stale(session):
    q = TaskQueue(session)
    t1 = q.enqueue("analyze")
    t2 = q.enqueue("analyze")
    q.fetch_next()  # t1 → running
    q.fetch_next()  # t2 → running
    n = q.reset_stale()
    assert n == 2
    session.refresh(t1); session.refresh(t2)
    assert t1.status == "queued"
    assert t2.status == "queued"
    assert t1.started_at is None
    assert t2.started_at is None


def test_count_by_status(session):
    q = TaskQueue(session)
    a = q.enqueue("analyze")
    b = q.enqueue("analyze")
    c = q.enqueue("analyze")
    q.fetch_next()              # a → running
    q.fetch_next()              # b → running
    q.mark_done(a.id)
    counts = q.count_by_status()
    assert counts.get("completed") == 1
    assert counts.get("running") == 1
    assert counts.get("queued") == 1


def test_fetch_empty_returns_none(session):
    q = TaskQueue(session)
    assert q.fetch_next() is None
