"""Celery tasks wrapping async forward/backward tracking."""
from __future__ import annotations

import logging

from celery import shared_task

_log = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def forward_track_task(self, paper_id: int, tenant_id: int, doi: str, refresh: bool = False) -> dict:
    """Fetch forward-tracking (cited-by) data for a paper."""
    try:
        from tracking.forward import ForwardTrackService
        svc = ForwardTrackService()
        result = svc.track(doi, refresh=refresh, from_paper_id=paper_id, tenant_id=tenant_id)
        _log.info("forward_track_task paper=%d doi=%s citing=%d", paper_id, doi, result.get("citing_count", 0))
        return {"status": "ok", "citing_count": result.get("citing_count", 0), "cached": result.get("cached")}
    except Exception as exc:
        _log.exception("forward_track_task failed paper=%d", paper_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def backward_track_task(self, paper_id: int, tenant_id: int, doi: str, refresh: bool = False) -> dict:
    """Fetch backward-tracking (references) data for a paper."""
    try:
        from tracking.backward import BackwardTrackService
        svc = BackwardTrackService()
        result = svc.track(doi, refresh=refresh, from_paper_id=paper_id, tenant_id=tenant_id)
        _log.info("backward_track_task paper=%d doi=%s refs=%d", paper_id, doi, result.get("references_count", 0))
        return {"status": "ok", "references_count": result.get("references_count", 0), "cached": result.get("cached")}
    except Exception as exc:
        _log.exception("backward_track_task failed paper=%d", paper_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=1)
def refresh_core_papers_task(self) -> dict:
    """Nightly: refresh tracking caches for all core papers across all tenants."""
    from datetime import timedelta, datetime, timezone
    from django.apps import apps

    try:
        Paper = apps.get_model("papers", "Paper")
    except LookupError:
        _log.warning("refresh_core_papers_task: papers app not installed")
        return {"status": "papers_app_missing"}

    forward_threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    core_papers = list(
        Paper.objects.filter(is_core=True).exclude(doi__isnull=True).exclude(doi="")
        .values_list("id", "doi", "tenant_id") if hasattr(Paper, "tenant_id")
        else Paper.objects.filter(is_core=True).exclude(doi__isnull=True).exclude(doi="")
        .values_list("id", "doi")
    )

    from tracking.models import ForwardTrackCache, BackwardTrackCache

    dispatched_fwd = dispatched_bw = 0
    for row in core_papers:
        if len(row) == 3:
            paper_id, doi, tenant_id = row
        else:
            paper_id, doi = row
            tenant_id = 1  # fallback for single-tenant legacy

        bw_exists = BackwardTrackCache.objects.filter(doi=doi).exists()
        if not bw_exists:
            backward_track_task.delay(paper_id, tenant_id, doi, refresh=True)
            dispatched_bw += 1

        fwd_stale = not ForwardTrackCache.objects.filter(doi=doi, fetched_at__gte=forward_threshold).exists()
        if fwd_stale:
            forward_track_task.delay(paper_id, tenant_id, doi, refresh=True)
            dispatched_fwd += 1

    _log.info("refresh_core_papers_task: fwd=%d bw=%d", dispatched_fwd, dispatched_bw)
    return {"dispatched_fwd": dispatched_fwd, "dispatched_bw": dispatched_bw}
