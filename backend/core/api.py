"""Root NinjaAPI instance.

Sub-agents (A · papers, B · discovery, C · accounts) attach their routers
here under their app namespace via `api.add_router("/<prefix>", router)`.

For now this only exposes /api/health. The contract is frozen in
docs/api-contract.yaml — paths and JSON shapes must match the Flask
endpoints they replace, so the Vue frontend (except the auth pages owned
by Agent D) keeps working unchanged.
"""
from __future__ import annotations

from ninja import NinjaAPI, Schema

api = NinjaAPI(
    title="KnowledgeBase API",
    version="1.0.0",
    description="Multi-tenant SaaS API. See docs/api-contract.yaml for the frozen contract.",
)


class HealthOut(Schema):
    status: str
    service: str


@api.get("/health", response=HealthOut, auth=None, tags=["meta"])
def health(request) -> HealthOut:
    return HealthOut(status="ok", service="kb-django")
