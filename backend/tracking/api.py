# Mount: api.add_router("", router, tags=["tracking"])
# (empty prefix because endpoints are nested under /papers/{id}/*)
from __future__ import annotations

from typing import Any, Dict, Optional

from ninja import Router, Schema
from ninja.security import django_auth

router = Router()


class TrackOut(Schema):
    status: str
    task_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


def _get_paper_doi(paper_id: int, tenant_id: int) -> Optional[str]:
    """Resolve DOI for a paper owned by the tenant."""
    from django.apps import apps
    try:
        Paper = apps.get_model("papers", "Paper")
    except LookupError:
        return None
    qs = Paper.objects.filter(pk=paper_id)
    # If Paper has tenant_id, scope it; otherwise trust paper_id
    if hasattr(Paper, "tenant"):
        qs = qs.filter(tenant_id=tenant_id)
    return qs.values_list("doi", flat=True).first()


@router.post("/papers/{paper_id}/forward-track", response={200: TrackOut, 202: TrackOut}, auth=django_auth)
def forward_track(request, paper_id: int, refresh: bool = False):
    """Trigger forward tracking. Returns 200+data if cached, else 202+task_id."""
    tenant_id = request.tenant.id
    doi = _get_paper_doi(paper_id, tenant_id)
    if not doi:
        return 404, {"status": "not_found"}

    from tracking.models import ForwardTrackCache
    from tracking.fetcher import normalize_doi
    doi_norm = normalize_doi(doi)
    cached = ForwardTrackCache.objects.filter(doi=doi_norm).first() if not refresh else None
    if cached:
        return 200, TrackOut(status="ok", data=cached.result_json)

    from tracking.tasks import forward_track_task
    task = forward_track_task.delay(paper_id, tenant_id, doi, refresh=refresh)
    return 202, TrackOut(status="queued", task_id=task.id)


@router.post("/papers/{paper_id}/backward-track", response={200: TrackOut, 202: TrackOut}, auth=django_auth)
def backward_track(request, paper_id: int, refresh: bool = False):
    """Trigger backward tracking. Returns 200+data if cached, else 202+task_id."""
    tenant_id = request.tenant.id
    doi = _get_paper_doi(paper_id, tenant_id)
    if not doi:
        return 404, {"status": "not_found"}

    from tracking.models import BackwardTrackCache
    from tracking.fetcher import normalize_doi
    doi_norm = normalize_doi(doi)
    cached = BackwardTrackCache.objects.filter(doi=doi_norm).first() if not refresh else None
    if cached:
        return 200, TrackOut(status="ok", data=cached.result_json)

    from tracking.tasks import backward_track_task
    task = backward_track_task.delay(paper_id, tenant_id, doi, refresh=refresh)
    return 202, TrackOut(status="queued", task_id=task.id)
