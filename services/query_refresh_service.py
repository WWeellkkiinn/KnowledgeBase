"""query_refresh_service — 已暂停。

依赖已删除的 SubscriptionResult 表。后续若需基于 ExplorePool 反馈
刷新检索式，再重写本模块。
"""
from __future__ import annotations

import logging
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def refresh_subscription_queries(db: Session, sub) -> dict:
    """No-op 桩。保留签名兼容 explore_service 的调用。"""
    return {"refreshed": False, "reason": "stubbed"}
