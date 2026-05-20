"""Celery task: AI paper analysis (F1+F2 tags + summary)."""
from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

_log = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def analyze_paper(self, paper_id: int) -> dict:
    """Run F1+F2 analysis on a Paper and save results."""
    from papers.models import Paper
    from .services.analyzer import analyze_paper as _analyze

    try:
        paper = Paper.objects.get(pk=paper_id)
    except Paper.DoesNotExist:
        _log.error("analyze_paper: paper %s not found", paper_id)
        return {"paper_id": paper_id, "status": "not_found"}

    title = paper.title or ""
    abstract = paper.abstract or ""

    if not title and not abstract:
        _log.warning("analyze_paper: paper %s has no title/abstract", paper_id)
        paper.ai_analyzed_at = timezone.now()
        paper.save(update_fields=["ai_analyzed_at"])
        return {"paper_id": paper_id, "status": "skipped"}

    try:
        result = _analyze(title, abstract)
    except Exception as exc:
        _log.exception("analyze_paper task failed paper_id=%s", paper_id)
        raise self.retry(exc=exc)

    if not result:
        paper.ai_analyzed_at = timezone.now()
        paper.save(update_fields=["ai_analyzed_at"])
        return {"paper_id": paper_id, "status": "empty"}

    updates = ["ai_analyzed_at"]
    tags = result.pop("tags", [])
    if tags:
        paper.ai_summary = paper.ai_summary or {}
        updates_needed = True
    paper.ai_summary = {k: v for k, v in result.items()}
    paper.ai_analyzed_at = timezone.now()
    updates.append("ai_summary")
    paper.save(update_fields=updates)

    # Sync tags as PaperTag relations
    if tags:
        _sync_tags(paper, tags)

    return {"paper_id": paper_id, "status": "analyzed", "tags": tags}


def _sync_tags(paper, tag_names: list[str]) -> None:
    from papers.models import Tag, PaperTag

    tenant = paper.tenant
    for name in tag_names:
        tag, _ = Tag.objects.get_or_create(tenant=tenant, name=name)
        PaperTag.objects.get_or_create(tenant=tenant, paper=paper, tag=tag)
