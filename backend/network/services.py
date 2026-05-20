"""Network graph query service."""
from __future__ import annotations

from typing import Optional

from .models import Edge


def get_edges(tenant_id: int, paper_id: Optional[int] = None, direction: Optional[str] = None) -> list[Edge]:
    qs = Edge.objects.filter(tenant_id=tenant_id)
    if paper_id is not None:
        qs = qs.filter(from_paper_id=paper_id)
    if direction:
        qs = qs.filter(direction=direction)
    return list(qs.order_by("from_paper_id", "to_paper_id"))


def to_cytoscape(edges: list[Edge]) -> dict:
    """Convert edge list to Cytoscape.js elements format."""
    node_ids: set[int] = set()
    for e in edges:
        node_ids.add(e.from_paper_id)
        node_ids.add(e.to_paper_id)

    nodes = [{"data": {"id": str(nid)}} for nid in sorted(node_ids)]
    edge_elements = [
        {
            "data": {
                "id": f"e{e.id}",
                "source": str(e.from_paper_id),
                "target": str(e.to_paper_id),
                "direction": e.direction,
            }
        }
        for e in edges
    ]
    return {"nodes": nodes, "edges": edge_elements}
