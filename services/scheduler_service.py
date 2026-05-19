from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from database import SessionLocal, models

_log = logging.getLogger(__name__)

_scheduler = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def start_scheduler(*, poll_seconds: int = 60) -> object:
    """启动 BackgroundScheduler（仅夜间维护任务）。重复调用安全。"""
    global _scheduler
    if _scheduler is not None and getattr(_scheduler, "running", False):
        return _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError as e:
        _log.warning("APScheduler not installed; scheduler disabled (%s)", e)
        return None

    sched = BackgroundScheduler(
        timezone="UTC",
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
    )

    def _daily_track_refresh():
        from sqlalchemy import outerjoin
        from services.task_queue import TaskQueue
        from services.upload_worker import (
            BACKWARD_TRACK_TYPE, FORWARD_TRACK_TYPE, wake_worker,
        )
        from services.reference_fetcher import normalize_doi as _ndoi
        from sqlalchemy import func as _func

        _FORWARD_REFRESH_AGE = timedelta(days=7)
        _COMMIT_BATCH = 50
        forward_threshold = _utcnow() - _FORWARD_REFRESH_AGE

        session = SessionLocal()
        enq_fwd = enq_bw = skipped_fresh = skipped_pending = 0
        any_enqueued = False
        try:
            doi_lower = _func.lower(_func.trim(models.Paper.doi))
            j = outerjoin(
                outerjoin(models.Paper, models.BackwardTrackCache, doi_lower == models.BackwardTrackCache.doi),
                models.ForwardTrackCache, doi_lower == models.ForwardTrackCache.doi,
            )
            rows = session.execute(
                select(
                    models.Paper.id, models.Paper.doi,
                    models.BackwardTrackCache.fetched_at.label("bw_fetched"),
                    models.ForwardTrackCache.fetched_at.label("fw_fetched"),
                ).select_from(j)
                .where(models.Paper.doi.isnot(None))
                .where(models.Paper.doi != "")
                .where(models.Paper.is_core.is_(True))
            ).all()
            pending_rows = session.execute(
                select(models.Task.paper_id, models.Task.type).where(
                    models.Task.type.in_((FORWARD_TRACK_TYPE, BACKWARD_TRACK_TYPE)),
                    models.Task.status.in_(("queued", "running")),
                )
            ).all()
            pending = {(pid, t) for pid, t in pending_rows}
            tq = TaskQueue(session)
            uncommitted = 0
            seen_papers: set = set()
            for paper_id, doi, bw_fetched, fw_fetched in rows:
                if paper_id in seen_papers:
                    continue
                seen_papers.add(paper_id)
                if not _ndoi((doi or "").strip()):
                    continue
                if (paper_id, BACKWARD_TRACK_TYPE) in pending:
                    skipped_pending += 1
                elif bw_fetched is None:
                    tq.enqueue(type=BACKWARD_TRACK_TYPE, paper_id=paper_id,
                               payload={"paper_id": paper_id, "refresh": True}, max_attempts=2)
                    enq_bw += 1
                    uncommitted += 1
                if (paper_id, FORWARD_TRACK_TYPE) in pending:
                    skipped_pending += 1
                elif fw_fetched is None or fw_fetched < forward_threshold:
                    tq.enqueue(type=FORWARD_TRACK_TYPE, paper_id=paper_id,
                               payload={"paper_id": paper_id, "refresh": True}, max_attempts=2)
                    enq_fwd += 1
                    uncommitted += 1
                else:
                    skipped_fresh += 1
                if uncommitted >= _COMMIT_BATCH:
                    session.commit()
                    any_enqueued = True
                    uncommitted = 0
            if uncommitted > 0:
                session.commit()
                any_enqueued = True
            _log.info("daily_track_refresh: enqueued fwd=%d bw=%d skipped fresh=%d pending=%d",
                      enq_fwd, enq_bw, skipped_fresh, skipped_pending)
        except Exception:
            session.rollback()
            _log.exception("daily_track_refresh failed")
        finally:
            session.close()
            if any_enqueued:
                wake_worker()

    def _daily_ai_batch():
        from services.ai_service import run_batch_analysis
        session = SessionLocal()
        try:
            result = run_batch_analysis(session)
            _log.info("daily_ai_batch done: %s", result)
        except Exception:
            _log.exception("daily_ai_batch failed")
        finally:
            session.close()

    def _daily_easyscholar_backfill():
        from services.easyscholar_service import backfill_stale
        session = SessionLocal()
        try:
            result = backfill_stale(session)
            _log.info("easyscholar_backfill done: %s", result)
        except Exception:
            _log.exception("easyscholar_backfill failed")
        finally:
            session.close()

    def _daily_venue_easyscholar_cache_refresh():  # noqa: secrets
        from services.easyscholar_service import fetch_from_api
        session = SessionLocal()
        try:
            cutoff = _utcnow() - timedelta(days=30)
            rows = session.execute(
                select(models.VenueEasyscholarCache).where(
                    or_(
                        models.VenueEasyscholarCache.fetched_at.is_(None),
                        models.VenueEasyscholarCache.fetched_at < cutoff,
                    )
                )
            ).scalars().all()
            success = failed = 0
            for row in rows:
                row.easyscholar_json = fetch_from_api(row.name)
                row.fetched_at = _utcnow()
                try:
                    session.commit()
                    success += 1
                except Exception:
                    session.rollback()
                    failed += 1
            _log.info("venue_easyscholar_cache_refresh done: success=%d failed=%d", success, failed)
        except Exception:
            _log.exception("venue_easyscholar_cache_refresh failed")
        finally:
            session.close()

    def _nightly_pipeline():
        """UTC 18:00（北京 02:00）：引用追踪 → AI 分析 → 期刊数据。"""
        _log.info("nightly_pipeline: step 1/3 track_refresh")
        _daily_track_refresh()
        _log.info("nightly_pipeline: step 2/3 ai_batch")
        _daily_ai_batch()
        _log.info("nightly_pipeline: step 3/3 easyscholar")
        _daily_easyscholar_backfill()
        _daily_venue_easyscholar_cache_refresh()  # noqa: secrets
        _log.info("nightly_pipeline: done")

    sched.add_job(
        _nightly_pipeline,
        trigger="cron",
        hour=18, minute=0,
        id="kb-nightly-pipeline",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    sched.start()
    _scheduler = sched
    _log.info("scheduler started (nightly pipeline only)")
    return sched


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and getattr(_scheduler, "running", False):
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
    _scheduler = None
