# Mount: api.add_router("/citations", router, tags=["citations"])
# Also: api.add_router("/papers", papers_citations_router, tags=["citations"])
"""Citations ninja router.

Endpoints (relative to their mount points):
  GET /api/papers/{id}/citations.bib  → paper_bibtex   (mounted under /papers)
  GET /api/citations.bib              → all_bibtex      (mounted under /citations)
"""
from __future__ import annotations

from django.http import HttpResponse, HttpRequest
from ninja import Router

from papers.models import Paper
from .services import generate_citation

# Router for /api/citations.bib (mounted at /citations)
router = Router()

# Router for paper-scoped citation routes (mounted at /papers)
papers_citations_router = Router()


def _get_tenant(request: HttpRequest):
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        from ninja.errors import HttpError
        raise HttpError(403, "Tenant context missing")
    return tenant


@papers_citations_router.get("/{paper_id}/citations.bib", url_name="paper_bibtex")
def paper_bibtex(request: HttpRequest, paper_id: int):
    from ninja.errors import HttpError
    tenant = _get_tenant(request)
    try:
        paper = Paper.objects.get(pk=paper_id, tenant=tenant)
    except Paper.DoesNotExist:
        raise HttpError(404, "Paper not found")
    result = generate_citation(paper)
    return HttpResponse(result["bibtex"], content_type="text/plain; charset=utf-8")


@router.get(".bib", url_name="all_bibtex")
def all_bibtex(request: HttpRequest):
    tenant = _get_tenant(request)
    papers = Paper.objects.filter(tenant=tenant).order_by("pk")
    entries = []
    for paper in papers:
        result = generate_citation(paper)
        if result.get("bibtex"):
            entries.append(result["bibtex"])
    content = "\n\n".join(entries)
    return HttpResponse(content, content_type="text/plain; charset=utf-8")
