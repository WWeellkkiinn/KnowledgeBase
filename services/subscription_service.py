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
    ) -> tuple[Optional[models.Subscription], bool]:
        """Returns (sub, description_changed).

        description_changed=True signals the caller to start _bg_recompute
        **after** committing, so the background thread reads the new description.
        """
        sub = session.get(models.Subscription, sub_id)
        if sub is None:
            return None, False
        if active is not None:
            sub.active = bool(active)
        description_changed = False
        if description is not None:
            new_desc = description.strip() or None
            if new_desc != sub.description:
                sub.description = new_desc
                sub.generated_queries = None
                description_changed = bool(new_desc)
                if new_desc:
                    from services.task_queue import TaskQueue
                    from services.upload_worker import GENERATE_QUERIES_TASK_TYPE
                    TaskQueue(session).enqueue(
                        GENERATE_QUERIES_TASK_TYPE,
                        payload={"subscription_id": sub.id},
                        max_attempts=2,
                    )
                    from services.explore_service import invalidate_query_cache
                    invalidate_query_cache(sub.id)
        session.flush()
        return sub, description_changed

    @staticmethod
    def delete(session: Session, sub_id: int) -> bool:
        sub = session.get(models.Subscription, sub_id)
        if sub is None:
            return False
        session.delete(sub)
        session.flush()
        return True
