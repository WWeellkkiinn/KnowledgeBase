# Mount: api.add_router("/explore", router, tags=["explore"])
from __future__ import annotations

from typing import Any, List, Optional

from ninja import Router, Schema
from ninja.security import django_auth

router = Router()


class ExploreCardData(Schema):
    pool_id: int
    title: str
    url: Optional[str]
    title_zh: Optional[str]
    display_date: str
    authors: str
    venue_name: Optional[str]
    rank_badges: List[dict] = []
    cited_by_count: Optional[int]
    tags: List[str]
    llm_reason: Optional[str]
    research_question: Optional[str]
    methodology: Optional[str]
    key_findings: List[str]
    bandit_score: Optional[float]


class ExploreCardOut(Schema):
    id: int
    card: ExploreCardData
    score: Optional[float]
    action: Optional[str]


class ActionIn(Schema):
    action: str  # "saved" | "skipped" | "passed"


class ExploreCardsResponse(Schema):
    items: List[ExploreCardOut]
    count: int
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
    raw = get_explore_cards(tenant_id, sub_id, limit=limit, exclude_ids=exclude_ids or None)
    items = []
    for c in raw:
        items.append({
            "id": c["id"],
            "score": c.get("bandit_score"),
            "action": c.get("action"),
            "card": {
                "pool_id": c["id"],
                "title": c.get("title") or "",
                "url": c.get("url") or None,
                "title_zh": c.get("title_zh") or None,
                "display_date": c.get("display_date") or "",
                "authors": c.get("authors") or "",
                "venue_name": c.get("venue_name") or None,
                "rank_badges": [],
                "cited_by_count": c.get("cited_by_count"),
                "tags": c.get("tags") or [],
                "llm_reason": c.get("llm_reason") or None,
                "research_question": c.get("research_question") or None,
                "methodology": c.get("methodology") or None,
                "key_findings": c.get("key_findings") or [],
                "bandit_score": c.get("bandit_score"),
            },
        })
    return ExploreCardsResponse(
        items=items,
        count=len(items),
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
