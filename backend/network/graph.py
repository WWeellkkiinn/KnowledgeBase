"""graph.py — write tracking results into network.Edge table.

Ported from services/graph_writer.py, adapted to Django ORM + tenant_id.
"""
from __future__ import annotations

import logging
from typing import Optional

_log = logging.getLogger(__name__)

_STEM_MAX = 120
_AUTHORS_MAX = 500


def write_tracking_results(
    tenant_id: int,
    from_paper_id: int,
    papers_data: list[dict],
    direction: str,
) -> int:
    """Upsert paper stubs and create edges. Returns count of new edges created."""
    from network.models import Edge

    existing_to_ids: set[int] = set(
        Edge.objects.filter(
            tenant_id=tenant_id,
            from_paper_id=from_paper_id,
            direction=direction,
        ).values_list("to_paper_id", flat=True)
    )

    new_edges: list[Edge] = []

    for item in papers_data:
        doi = (item.get("doi") or "").strip()
        if not doi:
            continue

        to_paper_id = _resolve_paper_id(doi, item)
        if to_paper_id is None:
            continue
        if to_paper_id in existing_to_ids:
            continue

        new_edges.append(Edge(
            tenant_id=tenant_id,
            from_paper_id=from_paper_id,
            to_paper_id=to_paper_id,
            direction=direction,
            ref_title=item.get("title") or "",
        ))
        existing_to_ids.add(to_paper_id)

    if new_edges:
        Edge.objects.bulk_create(new_edges, ignore_conflicts=True)

    _log.info("[graph] direction=%s from=%d added=%d edges", direction, from_paper_id, len(new_edges))
    return len(new_edges)


def _resolve_paper_id(doi: str, item: dict) -> Optional[int]:
    """Return paper.id for this DOI; create stub if absent.

    Papers table is owned by Agent A (papers app). We import it by app label
    to avoid a hard cross-app model dependency.
    """
    try:
        from django.apps import apps
        Paper = apps.get_model("papers", "Paper")
    except LookupError:
        _log.warning("[graph] papers app not installed, cannot resolve paper_id for doi=%s", doi)
        return None

    existing = Paper.objects.filter(doi=doi).values_list("id", flat=True).first()
    if existing:
        return existing

    stem = doi.replace("/", "_").replace(".", "_").replace(":", "_")[:_STEM_MAX]
    # Avoid stem collision
    if Paper.objects.filter(stem=stem).exists():
        stem = stem[:110] + "_" + doi[-8:].replace("/", "_")

    authors = item.get("authors")
    if isinstance(authors, str):
        authors_json = [a for a in authors[:_AUTHORS_MAX].split(", ") if a] or None
    elif isinstance(authors, list):
        authors_json = [str(a).strip() for a in authors if a][:50] or None
    else:
        authors_json = None

    try:
        paper = Paper.objects.create(
            stem=stem,
            doi=doi,
            title=item.get("title") or None,
            authors_json=authors_json,
            year=item.get("year"),
            status="pending",
            source="forward" if "forward" in (item.get("source") or "") else "ref",
        )
        return paper.id
    except Exception as exc:
        # IntegrityError race: another worker inserted same DOI
        existing = Paper.objects.filter(doi=doi).values_list("id", flat=True).first()
        if existing:
            return existing
        _log.warning("[graph] failed to create stub doi=%s: %s", doi, exc)
        return None
