# Mount: api.add_router("/papers", router, tags=["papers"])
"""Papers ninja router.

Endpoints:
  GET  /api/papers              → list_papers
  GET  /api/papers/{id}         → get_paper
  POST /api/papers/upload       → upload_paper
  POST /api/papers/{id}/ai-analyze → ai_analyze
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from django.http import HttpRequest
from ninja import File, Router, Schema
from ninja.files import UploadedFile
from ninja.pagination import paginate

from .models import Paper
from .tasks import process_upload

router = Router()

_ROOT = Path(__file__).resolve().parent.parent.parent
_PAPERS_DIR = _ROOT / "papers"


# ─── Schemas ──────────────────────────────────────────────────────────────────


class PaperOut(Schema):
    id: int
    stem: str
    doi: Optional[str] = None
    title: Optional[str] = None
    abstract: Optional[str] = None
    authors_json: Optional[list] = None
    year: Optional[int] = None
    journal_id: Optional[int] = None
    status: str
    source: str
    is_core: bool
    added_at: datetime
    analyzed_at: Optional[datetime] = None
    ai_summary: Optional[dict] = None
    ai_analyzed_at: Optional[datetime] = None


class UploadOut(Schema):
    task_id: str
    paper_id: int


class AiAnalyzeOut(Schema):
    task_id: str
    paper_id: int


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _get_tenant(request: HttpRequest):
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        from ninja.errors import HttpError
        raise HttpError(403, "Tenant context missing")
    return tenant


def _safe_filename(name: str) -> str:
    import re
    name = re.sub(r"[^\w.\-]", "_", name)
    return name[:200] or "upload"


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response=list[PaperOut], url_name="list_papers")
def list_papers(
    request: HttpRequest,
    status: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    tenant = _get_tenant(request)
    qs = Paper.objects.filter(tenant=tenant).order_by("-added_at")
    if status:
        qs = qs.filter(status=status)
    if source:
        qs = qs.filter(source=source)
    if q:
        qs = qs.filter(title__icontains=q)
    # Manual pagination (ninja @paginate decorator conflicts with custom params)
    total = qs.count()
    start = (page - 1) * page_size
    items = list(qs[start : start + page_size])
    return items


@router.get("/{paper_id}", response=PaperOut, url_name="get_paper")
def get_paper(request: HttpRequest, paper_id: int):
    from ninja.errors import HttpError
    tenant = _get_tenant(request)
    try:
        return Paper.objects.get(pk=paper_id, tenant=tenant)
    except Paper.DoesNotExist:
        raise HttpError(404, "Paper not found")


@router.post("/upload", response=UploadOut, url_name="upload_paper")
def upload_paper(request: HttpRequest, file: UploadedFile = File(...)):
    """Accept multipart PDF, save to disk, enqueue process_upload task."""
    from ninja.errors import HttpError
    tenant = _get_tenant(request)

    filename = _safe_filename(file.name or "upload.pdf")
    stem = Path(filename).stem

    # Compute SHA1 for duplicate detection
    content = file.read()
    sha1 = hashlib.sha1(content).hexdigest()

    existing = Paper.objects.filter(tenant=tenant, sha1=sha1).first()
    if existing:
        raise HttpError(409, f"Duplicate: paper #{existing.pk} has same SHA1")

    paper_dir = _PAPERS_DIR / stem
    paper_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = paper_dir / filename
    pdf_path.write_bytes(content)

    rel_pdf = pdf_path.relative_to(_ROOT).as_posix()

    paper = Paper.objects.create(
        tenant=tenant,
        stem=stem,
        pdf_path=rel_pdf,
        sha1=sha1,
        status=Paper.Status.PENDING,
        source=Paper.Source.ROOT,
    )

    task = process_upload.delay(paper.pk)
    return UploadOut(task_id=str(task.id), paper_id=paper.pk)


@router.post("/{paper_id}/ai-analyze", response=AiAnalyzeOut, url_name="ai_analyze")
def ai_analyze(request: HttpRequest, paper_id: int):
    from ninja.errors import HttpError
    tenant = _get_tenant(request)
    try:
        paper = Paper.objects.get(pk=paper_id, tenant=tenant)
    except Paper.DoesNotExist:
        raise HttpError(404, "Paper not found")

    from ai_analysis.tasks import analyze_paper as analyze_task
    task = analyze_task.delay(paper.pk)
    return AiAnalyzeOut(task_id=str(task.id), paper_id=paper.pk)
