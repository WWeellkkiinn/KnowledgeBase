"""SubscriptionService — 感兴趣领域管理（探索页配置来源）。

Subscription 只保留 description / generated_queries / active 三个业务字段，
调度执行逻辑已全部移除。探索池补充由 explore_service 实时触发。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
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
