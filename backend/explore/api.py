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


@router.get("", response=List[ExploreCardOut], auth=django_auth)
def get_explore(request, sub_id: int, limit: int = 10):
    """Return bandit-scored pool cards for a subscription."""
    tenant_id = request.tenant.id
    from explore.services import get_explore_cards
    cards = get_explore_cards(tenant_id, sub_id, limit=limit)
    return cards


@router.post("/{pool_id}/action", auth=django_auth)
def record_action(request, pool_id: int, payload: ActionIn):
    tenant_id = request.tenant.id
    from explore.services import record_explore_action
    try:
        result = record_explore_action(tenant_id, pool_id, payload.action)
    except ValueError as exc:
        return router.create_response(request, {"detail": str(exc)}, status=400)
    return result
