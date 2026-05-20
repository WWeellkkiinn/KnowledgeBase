"""Celery tasks for the papers app.

process_upload runs the MinerU upload pipeline:
  1) pdf2md  (Pdf2MdService / cloud)
  2) title   from MD first H1
  3) doi     resolver
  4) crossref metadata
  5) journal attach (via journals app)
  6) refs    extract_refs.py subprocess
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from celery import shared_task
from django.utils import timezone as dj_tz

from core.progress import publish as publish_progress
from .models import Paper
from .services.doi_resolver import resolve_doi
from .services.extract_refs import extract as extract_refs_from_md
from .services.pdf2md import Pdf2MdService
from .services.upload import compute_sha1, extract_title_from_md

_log = logging.getLogger(__name__)

# ─── path helpers ──────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
_PAPERS_DIR = _ROOT / "papers"

_DOI_ALLOWED_RE = re.compile(r"^10\.[0-9]{1,9}/[A-Za-z0-9._;()/:\-]+$")


def _abs_under_root(rel_or_abs: str | Path) -> Path:
    p = Path(rel_or_abs)
    abs_p = (p if p.is_absolute() else (_ROOT / p)).resolve()
    try:
        abs_p.relative_to(_PAPERS_DIR.resolve())
    except ValueError as e:
        raise ValueError(f"path escapes papers/: {rel_or_abs}") from e
    return abs_p


def _rel_to_root(p: Path) -> str:
    return p.resolve().relative_to(_ROOT.resolve()).as_posix()


# ─── metadata helpers ──────────────────────────────────────────────────────────


def _crossref_ua() -> str:
    email = os.environ.get("UNPAYWALL_EMAIL", "").strip()
    return f"KnowledgeBase/1.0 (mailto:{email})" if email else "KnowledgeBase/1.0"


def _crossref_metadata(doi: str, timeout: float = 10.0) -> dict:
    if not doi or not _DOI_ALLOWED_RE.match(doi):
        return {}
    encoded = urllib.parse.quote(doi, safe="")
    try:
        r = httpx.get(
            f"https://api.crossref.org/works/{encoded}",
            timeout=timeout,
            headers={"User-Agent": _crossref_ua()},
        )
        r.raise_for_status()
        msg = r.json().get("message") or {}
    except Exception as e:
        _log.info("crossref fetch failed for %s: %s", doi, e)
        return {}
    out: dict = {}
    issued = msg.get("issued") or {}
    parts = (issued.get("date-parts") or [[None]])[0]
    if parts and parts[0]:
        try:
            out["year"] = int(parts[0])
        except (TypeError, ValueError):
            pass
    authors_raw = msg.get("author") or []
    authors = []
    for a in authors_raw[:50]:
        family = a.get("family") or ""
        given = a.get("given") or ""
        full = (f"{given} {family}").strip()
        if full:
            authors.append(full)
    if authors:
        out["authors_json"] = authors
    if msg.get("title"):
        out["title"] = msg["title"][0] if isinstance(msg["title"], list) else str(msg["title"])
    if msg.get("abstract"):
        import html as _html
        raw = str(msg["abstract"])
        cleaned = re.sub(r"<[^>]*>", " ", raw)
        cleaned = _html.unescape(cleaned)
        cleaned = re.sub(r"<[^>]*>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        out["abstract"] = cleaned[:8000]
    return out


def _run_extract_refs(md_path: Path, out_path: Path) -> Optional[str]:
    """Import-based replacement for the old subprocess call."""
    try:
        refs = extract_refs_from_md(md_path)
    except Exception as exc:
        return str(exc)[:500] or "extract_refs failed"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(refs, ensure_ascii=False, indent=2), encoding="utf-8")
    return None


# ─── Celery task ───────────────────────────────────────────────────────────────


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_upload(self, paper_id: int) -> dict:
    """Upload pipeline for a Paper row.

    Stages: pdf2md → title → doi → crossref → journal → refs → analyzed.
    Returns {"paper_id": ..., "status": "analyzed"|"failed"}.

    Emits SSE progress events on channel ``progress:<task_id>`` (Celery task id).
    """
    task_id = self.request.id or ""

    def _emit(step: str, msg: str = "") -> None:
        publish_progress(task_id, {"task_id": task_id, "paper_id": paper_id, "step": step, "msg": msg})

    try:
        paper = Paper.objects.get(pk=paper_id)
    except Paper.DoesNotExist:
        _log.error("process_upload: paper %s not found", paper_id)
        _emit("error", "paper not found")
        return {"paper_id": paper_id, "status": "failed", "error": "not found"}

    paper.status = Paper.Status.PROCESSING
    paper.save(update_fields=["status"])
    _emit("start", "processing")

    try:
        if not paper.pdf_path:
            raise RuntimeError("paper.pdf_path empty")
        pdf_path = _abs_under_root(paper.pdf_path)
        if not pdf_path.exists():
            raise RuntimeError(f"PDF missing: {paper.pdf_path}")

        output_dir = pdf_path.parent

        # 1) PDF → MD via MinerU cloud
        _emit("pdf2md", "converting PDF")
        result = Pdf2MdService().convert(
            pdf_path,
            output_dir=output_dir,
            on_progress=lambda step, msg: _emit(f"pdf2md.{step}", msg),
        )
        if "error" in result:
            raise RuntimeError(f"pdf2md failed: {result['error']}")
        md_path = _abs_under_root(result["md_path"])
        paper.md_path = _rel_to_root(md_path)
        paper.save(update_fields=["md_path"])

        # 2) Title
        if not paper.title:
            title = extract_title_from_md(md_path)
            if title:
                paper.title = title
                paper.save(update_fields=["title"])
        _emit("title", paper.title or "")

        # 3) DOI
        if not paper.doi and paper.title:
            try:
                doi = resolve_doi(paper.title)
                if doi:
                    paper.doi = doi
                    paper.save(update_fields=["doi"])
            except Exception as e:
                _log.info("doi resolve failed: %s", e)
        _emit("doi", paper.doi or "")

        # 4) Crossref
        if paper.doi:
            meta = _crossref_metadata(paper.doi)
            updates = []
            if not paper.year and meta.get("year"):
                paper.year = meta["year"]
                updates.append("year")
            if not paper.authors_json and meta.get("authors_json"):
                paper.authors_json = meta["authors_json"]
                updates.append("authors_json")
            if not paper.abstract and meta.get("abstract"):
                paper.abstract = meta["abstract"]
                updates.append("abstract")
            if not paper.title and meta.get("title"):
                paper.title = meta["title"]
                updates.append("title")
            if updates:
                paper.save(update_fields=updates)
        _emit("crossref", "")

        # 5) Journal (journals app handles its own DB interactions)
        if paper.doi:
            try:
                from journals.services import attach_journal_to_paper  # type: ignore
                attach_journal_to_paper(paper)
            except Exception as e:
                _log.info("journal attach failed: %s", e)
        _emit("journal", "")

        # 6) Refs
        refs_path = output_dir / "refs.json"
        err = _run_extract_refs(md_path, refs_path)
        if err:
            _log.warning("extract_refs failed: %s", err)
        else:
            try:
                paper.refs_path = _rel_to_root(refs_path)
                paper.save(update_fields=["refs_path"])
            except ValueError:
                pass
        _emit("refs", "" if not err else f"warn: {err}")

        paper.status = Paper.Status.ANALYZED
        paper.analyzed_at = dj_tz.now()
        paper.save(update_fields=["status", "analyzed_at"])
        _emit("done", "analyzed")
        return {"paper_id": paper_id, "status": "analyzed"}

    except Exception as exc:
        _log.exception("process_upload failed paper_id=%s", paper_id)
        paper.status = Paper.Status.FAILED
        paper.failure_reason = str(exc)[:1000]
        paper.save(update_fields=["status", "failure_reason"])
        _emit("error", str(exc)[:200])
        raise self.retry(exc=exc)
