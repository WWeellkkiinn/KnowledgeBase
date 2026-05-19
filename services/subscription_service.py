"""SubscriptionService — 感兴趣领域管理（探索页配置来源）。

Subscription 只保留 description / generated_queries / active 三个业务字段，
调度执行逻辑已全部移除。探索池补充由 explore_service 实时触发。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from database import SessionLocal, models

_log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SubscriptionService:

    @staticmethod
    def list_all(session: Session, *, active_only: bool = False):
        stmt = select(models.Subscription).order_by(models.Subscription.id)
        if active_only:
            stmt = stmt.where(models.Subscription.active.is_(True))
        return list(session.execute(stmt).scalars().all())

    @staticmethod
    def get(session: Session, sub_id: int) -> Optional[models.Subscription]:
        return session.get(models.Subscription, sub_id)

    def create(
        self,
        session: Session,
        *,
        description: str = "",
        active: bool = True,
    ) -> models.Subscription:
        sub = models.Subscription(
            active=active,
            description=description.strip() or None,
            generated_queries=None,
        )
        session.add(sub)
        session.flush()
        if description.strip():
            from services.task_queue import TaskQueue
            from services.upload_worker import GENERATE_QUERIES_TASK_TYPE
            TaskQueue(session).enqueue(
                GENERATE_QUERIES_TASK_TYPE,
                payload={"subscription_id": sub.id},
                max_attempts=2,
            )
        return sub

    @staticmethod
    def update(
        session: Session,
        sub_id: int,
        *,
        active: Optional[bool] = None,
        description: Optional[str] = None,
    ) -> Optional[models.Subscription]:
        sub = session.get(models.Subscription, sub_id)
        if sub is None:
            return None
        if active is not None:
            sub.active = bool(active)
        if description is not None:
            new_desc = description.strip() or None
            if new_desc != sub.description:
                sub.description = new_desc
                sub.generated_queries = None
                if new_desc:
                    from services.task_queue import TaskQueue
                    from services.upload_worker import GENERATE_QUERIES_TASK_TYPE
                    TaskQueue(session).enqueue(
                        GENERATE_QUERIES_TASK_TYPE,
                        payload={"subscription_id": sub.id},
                        max_attempts=2,
                    )
                    from services.explore_service import invalidate_query_cache, _compute_pre_scores
                    import threading as _t
                    from database import SessionLocal as _SL
                    invalidate_query_cache(sub.id)
                    def _bg_recompute(sid):
                        s = _SL()
                        try:
                            _compute_pre_scores(s, sid)
                        finally:
                            s.close()
                    _t.Thread(target=_bg_recompute, args=(sub.id,), daemon=True).start()
        session.flush()
        return sub

    @staticmethod
    def delete(session: Session, sub_id: int) -> bool:
        sub = session.get(models.Subscription, sub_id)
        if sub is None:
            return False
        session.delete(sub)
        session.flush()
        return True


def _score_batch(db: Session, description: str, batch: list) -> None:
    """5 篇/批 LLM 内容生成（title_zh / tags / reason 等）。失败整批抛异常，由调用方决定重试。"""
    import json
    import re as _re
    from services.ai_service import _sanitize_tags, _sanitize_text, _sanitize_findings
    from services.llm_client import chat_completion as _call_llm
    from datetime import datetime as _dt, timezone as _tz

    payload = []
    for idx, r in enumerate(batch):
        meta = r.raw_metadata_json or {}
        payload.append({
            "idx": idx,
            "title": (meta.get("title") or "")[:200],
            "abstract": (meta.get("abstract") or "")[:600],
        })
    sys_prompt = (
        "你是学术论文晨报助手。目标读者是忙碌的研究者，需要在10秒内判断一篇论文是否值得打开。\n"
        "对输入论文列表中的每篇，输出一个 JSON 数组项，包含：\n"
        "- idx: 输入论文的索引（int）\n"
        "- reason: <=80 字，说明为什么值得或不值得推送（不用学术语气）\n"
        "- title_zh: 中文翻译标题\n"
        '- tags: 2-4 字中文标签数组，最多 4 个（如 ["机器学习", "宏观经济"]）\n'
        "- research_question: ≤40 字，用普通中文说清楚【这篇文章在问什么】，不用学术语气，不写【本文】\n"
        "- methodology: ≤50 字，说【它怎么做】，遇到专业术语立刻用括号解释\n"
        "- key_findings: 中文数组，最多 3 条，每条≤35 字，说【能用它做什么/有什么用】，偏应用价值，不写【本文提出/本文研究】\n\n"
        "只输出 JSON 数组，无 markdown 围栏、无说明。"
    )
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": (
            f"用户研究兴趣：\n{description}\n\n"
            f"论文列表：\n{json.dumps(payload, ensure_ascii=False)}"
        )},
    ]
    raw = _call_llm(messages, max_tokens=4096)
    match = _re.search(r"\[[\s\S]*\]", raw)
    if not match:
        raise ValueError("no JSON array")
    arr = json.loads(match.group())
    now = _dt.now(_tz.utc).replace(tzinfo=None)
    by_idx = {int(item["idx"]): item for item in arr if isinstance(item, dict) and "idx" in item}
    for idx, r in enumerate(batch):
        info = by_idx.get(idx, {})
        reason = info.get("reason")
        if isinstance(reason, str):
            r.llm_reason = reason[:500]
        r.title_zh = _sanitize_text(info.get("title_zh")) or None
        tags = _sanitize_tags(info.get("tags"))
        r.tags_json = tags if tags else None
        r.research_question = _sanitize_text(info.get("research_question")) or None
        r.methodology = _sanitize_text(info.get("methodology")) or None
        findings = _sanitize_findings(info.get("key_findings"))
        r.key_findings_json = findings if findings else None
        r.scored_at = now


_scheduler = None


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
