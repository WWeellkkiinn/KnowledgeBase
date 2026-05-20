"""Subscription CRUD service — ported from services/subscription_service.py."""
from __future__ import annotations

import logging
from typing import Optional

from .models import Subscription

_log = logging.getLogger(__name__)


def list_subscriptions(tenant_id: int, *, active_only: bool = False):
    qs = Subscription.objects.filter(tenant_id=tenant_id).order_by("id")
    if active_only:
        qs = qs.filter(active=True)
    return list(qs)


def get_subscription(tenant_id: int, sub_id: int) -> Optional[Subscription]:
    try:
        return Subscription.objects.get(pk=sub_id, tenant_id=tenant_id)
    except Subscription.DoesNotExist:
        return None


def create_subscription(
    tenant_id: int,
    *,
    description: str = "",
    sub_type: str = "topic_search",
    target_ref: str = "",
    active: bool = True,
) -> Subscription:
    sub = Subscription.objects.create(
        tenant_id=tenant_id,
        description=description.strip(),
        sub_type=sub_type,
        target_ref=target_ref.strip(),
        active=active,
    )
    if description.strip():
        from subscriptions.tasks import generate_queries_task
        generate_queries_task.delay(sub.id)
    return sub


def update_subscription(
    tenant_id: int,
    sub_id: int,
    *,
    active: Optional[bool] = None,
    description: Optional[str] = None,
    target_ref: Optional[str] = None,
) -> Optional[Subscription]:
    sub = get_subscription(tenant_id, sub_id)
    if sub is None:
        return None
    if active is not None:
        sub.active = bool(active)
    if description is not None:
        new_desc = description.strip()
        if new_desc != sub.description:
            sub.description = new_desc
            sub.generated_queries = None
            if new_desc:
                from subscriptions.tasks import generate_queries_task
                generate_queries_task.delay(sub.id)
    if target_ref is not None:
        sub.target_ref = target_ref.strip()
    sub.save()
    return sub


def delete_subscription(tenant_id: int, sub_id: int) -> bool:
    deleted, _ = Subscription.objects.filter(pk=sub_id, tenant_id=tenant_id).delete()
    return deleted > 0
