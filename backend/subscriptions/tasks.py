"""Celery tasks for subscriptions — replaces APScheduler from scheduler_service.py."""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task

_log = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def generate_queries_task(self, subscription_id: int) -> dict:
    """Generate LLM search queries for a subscription description."""
    try:
        from subscriptions.models import Subscription
        sub = Subscription.objects.get(pk=subscription_id)
    except Exception as exc:
        _log.warning("generate_queries_task: sub %d not found: %s", subscription_id, exc)
        return {"status": "not_found"}

    if not sub.description:
        return {"status": "no_description"}

    try:
        from subscriptions.llm_query_gen import generate_queries
        queries = generate_queries(sub.description)
        sub.generated_queries = queries
        sub.save(update_fields=["generated_queries"])
        _log.info("generate_queries_task: sub=%d queries=%d", subscription_id, len(queries))
        return {"status": "ok", "count": len(queries)}
    except Exception as exc:
        _log.exception("generate_queries_task failed sub=%d", subscription_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=1)
def nightly_fill_explore_pools(self) -> dict:
    """Fill explore pools for all active subscriptions. Triggered by Celery Beat at 02:00 UTC."""
    from subscriptions.models import Subscription
    from explore.tasks import fill_pool_task

    subs = list(Subscription.objects.filter(active=True).values_list("id", flat=True))
    for sub_id in subs:
        fill_pool_task.delay(sub_id)
    _log.info("nightly_fill_explore_pools: dispatched %d fill tasks", len(subs))
    return {"dispatched": len(subs)}


@shared_task(bind=True, max_retries=1)
def nightly_track_refresh(self) -> dict:
    """Refresh forward/backward tracking caches for all core papers."""
    from tracking.tasks import refresh_core_papers_task
    refresh_core_papers_task.delay()
    return {"status": "dispatched"}


# ─── Celery Beat schedule (registered in SETTINGS_PATCH.md) ─────────────────
# CELERY_BEAT_SCHEDULE entry names match task module paths so Beat can find them.
BEAT_SCHEDULE = {
    "nightly-fill-explore-pools": {
        "task": "subscriptions.tasks.nightly_fill_explore_pools",
        "schedule": {"hour": 2, "minute": 0},  # 02:00 UTC
        "options": {"expires": 3600},
    },
    "nightly-track-refresh": {
        "task": "subscriptions.tasks.nightly_track_refresh",
        "schedule": {"hour": 2, "minute": 30},  # 02:30 UTC, after pool fill
        "options": {"expires": 3600},
    },
}
