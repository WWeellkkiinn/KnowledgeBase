# Mount: api.add_router("/explore", router, tags=["explore"])
from __future__ import annotations

from typing import Any, List, Optional

from ninja import Router, Schema
from ninja.security import django_auth

router = Router()


class ExploreCardOut(Schema):
    id: int
    title: str
    url: str
    title_zh: str
    display_date: str
    authors: str
    cited_by_count: Optional[int]
    venue_name: str
    tags: List[str]
    research_question: str
    methodology: str
    key_findings: List[str]
    llm_reason: str
    llm_pending: bool
    bandit_score: Optional[float]
    action: Optional[str]


class ActionIn(Schema):
    action: str  # "saved" | "skipped" | "passed"


class ExploreCardsResponse(Schema):
    items: List[ExploreCardOut]
    pool_count: int
    is_filling: bool


def _pool_count(tenant_id: int, sub_id: int) -> int:
    from explore.models import ExplorePool
    return ExplorePool.objects.filter(
        tenant_id=tenant_id,
        subscription_id=sub_id,
        action__isnull=True,
        scored_at__isnull=False,
    ).count()


@router.get("/cards", response=ExploreCardsResponse, auth=django_auth)
def get_cards(request, sub_id: int, limit: int = 10, exclude: str = ""):
    """Return bandit-scored pool cards for a subscription."""
    tenant_id = request.tenant.id
    from explore.services import get_explore_cards
    exclude_ids: List[int] = []
    if exclude:
        for chunk in exclude.split(","):
            chunk = chunk.strip()
            if chunk.isdigit():
                exclude_ids.append(int(chunk))
    cards = get_explore_cards(tenant_id, sub_id, limit=limit, exclude_ids=exclude_ids or None)
    return ExploreCardsResponse(
        items=cards,
        pool_count=_pool_count(tenant_id, sub_id),
        is_filling=False,
    )


@router.post("/{pool_id}/action", auth=django_auth)
def record_action(request, pool_id: int, payload: ActionIn):
    tenant_id = request.tenant.id
    from explore.services import record_explore_action
    try:
        result = record_explore_action(tenant_id, pool_id, payload.action)
    except ValueError as exc:
        return router.create_response(request, {"detail": str(exc)}, status=400)
    return {"ok": True, "paper_id": result.get("pool_id")}


@router.post("/{pool_id}/undo", auth=django_auth)
def undo_action(request, pool_id: int):
    tenant_id = request.tenant.id
    from explore.models import ExplorePool
    try:
        item = ExplorePool.objects.get(pk=pool_id, tenant_id=tenant_id)
    except ExplorePool.DoesNotExist:
        return router.create_response(request, {"detail": "not found"}, status=404)
    if item.action:
        item.action = None
        item.acted_at = None
        item.save(update_fields=["action", "acted_at"])
    return {"ok": True}
