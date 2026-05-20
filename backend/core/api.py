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

# ── Domain routers (mounted in dependency-free order) ────────────────
# Each app exposes its own ninja Router; main agent merges the mounts here.
from accounts.api import router as auth_router  # noqa: E402

# Agent A — Papers Domain
from papers.api import router as papers_router  # noqa: E402
from citations.api import router as citations_router  # noqa: E402
from citations.api import papers_citations_router  # noqa: E402

# Agent B — Discovery Domain
from subscriptions.api import router as subscriptions_router  # noqa: E402
from explore.api import router as explore_router  # noqa: E402
from network.api import router as network_router  # noqa: E402
from tracking.api import router as tracking_router  # noqa: E402

api.add_router("/auth", auth_router, tags=["auth"])
api.add_router("/papers", papers_router, tags=["papers"])
api.add_router("/papers", papers_citations_router, tags=["citations"])
api.add_router("/citations", citations_router, tags=["citations"])
api.add_router("/subscriptions", subscriptions_router, tags=["subscriptions"])
api.add_router("/explore", explore_router, tags=["explore"])
api.add_router("/network", network_router, tags=["network"])
# tracking exposes absolute paths like /papers/{id}/forward-track; empty prefix
api.add_router("", tracking_router, tags=["tracking"])


class HealthOut(Schema):
    status: str
    service: str


@api.get("/health", response=HealthOut, auth=None, tags=["meta"])
def health(request) -> HealthOut:
    return HealthOut(status="ok", service="kb-django")
