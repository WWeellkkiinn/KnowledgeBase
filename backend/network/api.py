# Mount: api.add_router("/network", router, tags=["network"])
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ninja import Router, Schema
from ninja.security import django_auth

router = Router()


class NodeData(Schema):
    id: str


class EdgeData(Schema):
    id: str
    source: str
    target: str
    direction: str


class CytoscapeNode(Schema):
    data: NodeData


class CytoscapeEdge(Schema):
    data: EdgeData


class CytoscapeOut(Schema):
    nodes: List[CytoscapeNode]
    edges: List[CytoscapeEdge]


@router.get("/edges", response=CytoscapeOut, auth=django_auth)
def get_edges(request, paper_id: Optional[int] = None, direction: Optional[str] = None):
    """Return citation graph in Cytoscape.js elements format."""
    tenant_id = request.tenant.id
    from network.services import get_edges, to_cytoscape
    edges = get_edges(tenant_id, paper_id=paper_id, direction=direction)
    return to_cytoscape(edges)
