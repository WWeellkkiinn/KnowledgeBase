"""Celery tasks for explore pool filling and LLM scoring."""
from __future__ import annotations

import logging

from celery import shared_task

_log = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def fill_pool_task(self, sub_id: int) -> dict:
    """Fill explore pool for one subscription."""
    try:
        from subscriptions.models import Subscription
        sub = Subscription.objects.get(pk=sub_id)
    except Exception:
        return {"status": "not_found"}

    try:
        from explore.services import fill_explore_pool
        result = fill_explore_pool(sub.tenant_id, sub_id)
        _log.info("fill_pool_task sub=%d: %s", sub_id, result)
        return result
    except Exception as exc:
        _log.exception("fill_pool_task failed sub=%d", sub_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=1)
def score_pending_task(self, tenant_id: int, sub_id: int) -> dict:
    """LLM-score unscored pool items, 5 papers per batch."""
    from explore.models import ExplorePool
    from explore.services import score_batch
    from subscriptions.models import Subscription

    try:
        sub = Subscription.objects.get(pk=sub_id, tenant_id=tenant_id)
    except Subscription.DoesNotExist:
        return {"status": "not_found"}
    description = (sub.description or "").strip()
    if not description:
        return {"status": "no_description"}

    pending_ids = list(
        ExplorePool.objects.filter(
            tenant_id=tenant_id,
            subscription_id=sub_id,
            scored_at__isnull=True,
            action__isnull=True,
        ).values_list("id", flat=True)[:120]
    )
    if not pending_ids:
        return {"scored": 0}

    _log.info("score_pending_task: %d items to score for sub=%d", len(pending_ids), sub_id)
    total_scored = total_failed = 0
    batch_size = 5
    for i in range(0, len(pending_ids), batch_size):
        batch = pending_ids[i:i + batch_size]
        result = score_batch(tenant_id, sub_id, description, batch)
        total_scored += result.get("scored", 0)
        total_failed += result.get("failed", 0)
    return {"scored": total_scored, "failed": total_failed}
