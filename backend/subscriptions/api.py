# Mount: api.add_router("/subscriptions", router, tags=["subscriptions"])
from __future__ import annotations

from typing import List, Optional

from ninja import Router, Schema
from ninja.security import django_auth

from .services import (
    create_subscription,
    delete_subscription,
    get_subscription,
    list_subscriptions,
    update_subscription,
)

router = Router()


class SubscriptionIn(Schema):
    description: str = ""
    sub_type: str = "topic_search"
    target_ref: str = ""
    active: bool = True


class SubscriptionPatch(Schema):
    description: Optional[str] = None
    active: Optional[bool] = None
    target_ref: Optional[str] = None


class SubscriptionOut(Schema):
    id: int
    tenant_id: int
    sub_type: str
    description: str
    target_ref: str
    active: bool
    generated_queries: Optional[List[str]]


def _out(sub) -> SubscriptionOut:
    return SubscriptionOut(
        id=sub.id,
        tenant_id=sub.tenant_id,
        sub_type=sub.sub_type,
        description=sub.description,
        target_ref=sub.target_ref,
        active=sub.active,
        generated_queries=sub.generated_queries,
    )


def _tenant_id(request) -> int:
    return request.tenant.id  # set by TenantContextMiddleware


class SubscriptionList(Schema):
    items: List[SubscriptionOut]
    total: int


@router.get("", response=SubscriptionList, auth=django_auth)
def list_subs(request, active: Optional[int] = None):
    items = [
        _out(s)
        for s in list_subscriptions(_tenant_id(request), active_only=bool(active))
    ]
    return SubscriptionList(items=items, total=len(items))


@router.post("", response=SubscriptionOut, auth=django_auth)
def create_sub(request, payload: SubscriptionIn):
    sub = create_subscription(
        _tenant_id(request),
        description=payload.description,
        sub_type=payload.sub_type,
        target_ref=payload.target_ref,
        active=payload.active,
    )
    return _out(sub)


@router.get("/{sub_id}", response=SubscriptionOut, auth=django_auth)
def get_sub(request, sub_id: int):
    sub = get_subscription(_tenant_id(request), sub_id)
    if sub is None:
        return router.create_response(request, {"detail": "not found"}, status=404)
    return _out(sub)


@router.patch("/{sub_id}", response=SubscriptionOut, auth=django_auth)
def patch_sub(request, sub_id: int, payload: SubscriptionPatch):
    sub = update_subscription(
        _tenant_id(request),
        sub_id,
        active=payload.active,
        description=payload.description,
        target_ref=payload.target_ref,
    )
    if sub is None:
        return router.create_response(request, {"detail": "not found"}, status=404)
    return _out(sub)


@router.delete("/{sub_id}", auth=django_auth)
def delete_sub(request, sub_id: int):
    ok = delete_subscription(_tenant_id(request), sub_id)
    if not ok:
        return router.create_response(request, {"detail": "not found"}, status=404)
    return {"deleted": True}
