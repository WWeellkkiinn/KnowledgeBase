# Mount: api.add_router("/network", router, tags=["network"])
from __future__ import annotations

from typing import List, Optional

from ninja import Router, Schema
from ninja.security import django_auth

router = Router()


@router.get("", auth=django_auth)
def get_graph(request, limit: int = 1000):
    """Rich citation graph for the active tenant."""
    from collections import Counter
    from network.models import Edge
    from papers.models import Paper

    tenant_id = request.tenant.id

    edges_qs = list(
        Edge.objects.filter(tenant_id=tenant_id).values(
            "id", "from_paper_id", "to_paper_id"
        )
    )

    paper_qs = Paper.objects.filter(tenant_id=tenant_id).select_related("journal")
    total = paper_qs.count()
    papers = list(paper_qs.order_by("id")[:limit])
    truncated = total > limit

    incoming = Counter(e["to_paper_id"] for e in edges_qs)
    kept_ids = {p.id for p in papers}

    nodes = [
        {
            "id": p.id,
            "stem": p.stem,
            "title": p.title,
            "year": p.year,
            "status": p.status,
            "source": p.source,
            "quality_tier": p.journal.quality_tier if p.journal else None,
            "authors_json": p.authors_json if isinstance(p.authors_json, list) else None,
            "citation_count": int(incoming.get(p.id, 0)),
        }
        for p in papers
    ]
    edges = [
        {"id": e["id"], "from": e["from_paper_id"], "to": e["to_paper_id"]}
        for e in edges_qs
        if e["from_paper_id"] in kept_ids and e["to_paper_id"] in kept_ids
    ]
    return {"nodes": nodes, "edges": edges, "total": total, "truncated": truncated}


class _CytoNodeData(Schema):
    id: str


class _CytoEdgeData(Schema):
    id: str
    source: str
    target: str
    direction: str


class _CytoNode(Schema):
    data: _CytoNodeData


class _CytoEdge(Schema):
    data: _CytoEdgeData


class CytoscapeOut(Schema):
    nodes: List[_CytoNode]
    edges: List[_CytoEdge]


@router.get("/edges", response=CytoscapeOut, auth=django_auth)
def get_edges(request, paper_id: Optional[int] = None, direction: Optional[str] = None):
    """Cytoscape.js elements format — kept for legacy callers."""
    tenant_id = request.tenant.id
    from network.services import get_edges as svc_get_edges, to_cytoscape
    edges = svc_get_edges(tenant_id, paper_id=paper_id, direction=direction)
    return to_cytoscape(edges)
