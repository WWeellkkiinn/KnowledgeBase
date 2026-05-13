"""M2.3 验收：SubscriptionService CRUD + run_due + scheduler 启停。"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from database import Base, enable_sqlite_foreign_keys, models
from services.subscription_service import (
    SubscriptionService,
    _utcnow,
    parse_simple_interval,
    start_scheduler,
    stop_scheduler,
)


@pytest.fixture()
def session(tmp_path: Path):
    db_file = tmp_path / "kb_sub.db"
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


# ─── 间隔解析 ───────────────────────────────────────────────────────


def test_parse_simple_interval():
    assert parse_simple_interval("every 5m") == timedelta(minutes=5)
    assert parse_simple_interval("3h") == timedelta(hours=3)
    assert parse_simple_interval("every 2d") == timedelta(days=2)
    assert parse_simple_interval("") == timedelta(days=7)


def test_parse_simple_interval_supports_cron():
    """标准 cron 表达式应交给 APScheduler CronTrigger 计算下次触发时间。"""
    # 每周一 3:00 UTC：下次触发距 now 必在 (0, 7天]，不应再静默回退到 7d
    delta = parse_simple_interval("0 3 * * 1")
    assert timedelta(0) < delta <= timedelta(days=8)


def test_parse_simple_interval_rejects_negative():
    """负数 / 0 应回退 7 天，避免 next_run_at 永远 <= now 触发死循环。"""
    assert parse_simple_interval("every -5m") == timedelta(days=7)
    assert parse_simple_interval("0m") == timedelta(days=7)


# ─── CRUD ────────────────────────────────────────────────────────────


def test_create_paper_citations(session):
    svc = SubscriptionService()
    sub = svc.create(session, type="paper_citations",
                     target={"doi": "10.1/X"}, cron_expr="every 7d")
    assert sub.id is not None
    assert sub.active is True
    assert sub.next_run_at is not None
    assert sub.target_json == {"doi": "10.1/X"}


def test_create_rejects_invalid_type(session):
    with pytest.raises(ValueError, match="unsupported"):
        SubscriptionService().create(session, type="bogus",
                                     target={}, cron_expr="every 1d")


def test_create_validates_target_paper_citations(session):
    with pytest.raises(ValueError, match="doi"):
        SubscriptionService().create(session, type="paper_citations",
                                     target={}, cron_expr="every 1d")


def test_create_validates_target_author_works(session):
    with pytest.raises(ValueError, match="author_id"):
        SubscriptionService().create(session, type="author_works",
                                     target={}, cron_expr="every 1d")


def test_create_validates_target_topic_search(session):
    with pytest.raises(ValueError, match="query"):
        SubscriptionService().create(session, type="topic_search",
                                     target={}, cron_expr="every 1d")


def test_update_cron_recalcs_next_run(session):
    svc = SubscriptionService()
    sub = svc.create(session, type="paper_citations",
                     target={"doi": "10.1/x"}, cron_expr="every 7d")
    old = sub.next_run_at
    svc.update(session, sub.id, cron_expr="every 1d")
    assert sub.next_run_at < old


def test_update_target_re_validates(session):
    svc = SubscriptionService()
    sub = svc.create(session, type="paper_citations",
                     target={"doi": "10.1/x"}, cron_expr="every 1d")
    with pytest.raises(ValueError):
        svc.update(session, sub.id, target={})


def test_delete_returns_true(session):
    svc = SubscriptionService()
    sub = svc.create(session, type="paper_citations",
                     target={"doi": "10.1/x"}, cron_expr="every 1d")
    assert svc.delete(session, sub.id) is True
    assert svc.delete(session, sub.id) is False


def test_list_filters_active(session):
    svc = SubscriptionService()
    a = svc.create(session, type="paper_citations",
                   target={"doi": "10.1/a"}, cron_expr="every 1d")
    b = svc.create(session, type="paper_citations",
                   target={"doi": "10.1/b"}, cron_expr="every 1d", active=False)
    all_subs = svc.list_all(session)
    actives = svc.list_all(session, active_only=True)
    assert {s.id for s in all_subs} == {a.id, b.id}
    assert {s.id for s in actives} == {a.id}


# ─── run_due ────────────────────────────────────────────────────────


def test_run_due_executes_only_due_subscriptions(session, monkeypatch):
    svc = SubscriptionService()
    due = svc.create(session, type="paper_citations",
                     target={"doi": "10.1/due"}, cron_expr="every 1d")
    due.next_run_at = _utcnow() - timedelta(minutes=1)
    not_yet = svc.create(session, type="paper_citations",
                         target={"doi": "10.1/notyet"}, cron_expr="every 1d")
    not_yet.next_run_at = _utcnow() + timedelta(days=1)
    session.flush()

    from services import forward_track_service as fts_mod
    monkeypatch.setattr(fts_mod.ForwardTrackService, "track",
                        lambda self, doi, **kw: {
                            "doi": doi, "citing_papers": [
                                {"doi": "10.1/cite1", "title": "C1", "year": 2024,
                                 "authors": "A", "source": "ss"},
                            ],
                            "cached": False, "citing_count": 1, "fetched_at": "z",
                        })

    report = svc.run_due(session=session)
    assert report["ran"] == 1
    assert report["found"] == 1

    results = session.execute(select(models.SubscriptionResult)).scalars().all()
    assert len(results) == 1
    assert results[0].subscription_id == due.id
    assert results[0].notified is False


def test_run_due_dedups_by_doi_across_runs(session, monkeypatch):
    svc = SubscriptionService()
    sub = svc.create(session, type="paper_citations",
                     target={"doi": "10.1/root"}, cron_expr="every 1d")
    sub.next_run_at = _utcnow() - timedelta(minutes=1)
    session.flush()

    citing = [{"doi": "10.1/c1", "title": "T1", "year": 2024,
               "authors": "", "source": "ss"}]
    from services import forward_track_service as fts_mod
    monkeypatch.setattr(fts_mod.ForwardTrackService, "track",
                        lambda self, doi, **kw: {
                            "doi": doi, "citing_papers": citing,
                            "cached": False, "citing_count": 1, "fetched_at": "z",
                        })

    svc.run_due(session=session)
    sub.next_run_at = _utcnow() - timedelta(minutes=1)  # 模拟下一周期到期
    session.flush()
    svc.run_due(session=session)

    results = session.execute(select(models.SubscriptionResult)).scalars().all()
    assert len(results) == 1  # 不重复写


def test_run_due_continues_on_failure(session, monkeypatch):
    svc = SubscriptionService()
    s1 = svc.create(session, type="paper_citations",
                    target={"doi": "10.1/a"}, cron_expr="every 1d")
    s2 = svc.create(session, type="paper_citations",
                    target={"doi": "10.1/b"}, cron_expr="every 1d")
    s1.next_run_at = _utcnow() - timedelta(minutes=1)
    s2.next_run_at = _utcnow() - timedelta(minutes=1)
    session.flush()

    calls = {"n": 0}

    def fake_track(self, doi, **kw):
        calls["n"] += 1
        if doi == "10.1/a":
            raise RuntimeError("simulated SS down")
        return {"doi": doi, "citing_papers": [], "cached": False,
                "citing_count": 0, "fetched_at": "z"}

    from services import forward_track_service as fts_mod
    monkeypatch.setattr(fts_mod.ForwardTrackService, "track", fake_track)

    report = svc.run_due(session=session)
    assert report["errors"] == 1
    assert report["ran"] == 1  # 第二条仍然跑通
    assert calls["n"] == 2


def test_run_due_updates_next_run_at(session, monkeypatch):
    svc = SubscriptionService()
    sub = svc.create(session, type="paper_citations",
                     target={"doi": "10.1/x"}, cron_expr="every 1d")
    sub.next_run_at = _utcnow() - timedelta(minutes=1)
    session.flush()

    from services import forward_track_service as fts_mod
    monkeypatch.setattr(fts_mod.ForwardTrackService, "track",
                        lambda self, doi, **kw: {
                            "doi": doi, "citing_papers": [],
                            "cached": False, "citing_count": 0, "fetched_at": "z",
                        })

    svc.run_due(session=session)
    assert sub.last_run_at is not None
    assert sub.next_run_at > _utcnow()


def test_unimplemented_types_dont_crash(session):
    svc = SubscriptionService()
    sub = svc.create(session, type="author_works",
                     target={"author_id": "A123"}, cron_expr="every 1d")
    sub.next_run_at = _utcnow() - timedelta(minutes=1)
    session.flush()
    report = svc.run_due(session=session)
    assert report["errors"] == 0
    assert report["found"] == 0


# ─── Scheduler 启停 ─────────────────────────────────────────────────


def test_scheduler_start_idempotent():
    s1 = start_scheduler(poll_seconds=3600)
    s2 = start_scheduler(poll_seconds=3600)
    try:
        assert s1 is s2
    finally:
        stop_scheduler()


def test_scheduler_stop_safe_when_not_running():
    stop_scheduler()
    stop_scheduler()  # 重复调用不应抛
