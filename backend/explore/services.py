"""Explore service — ported from services/explore_service.py.

Adapted to Django ORM + tenant_id scoping.
Heavy LLM + HTTP logic is preserved; threading model kept intact.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from .bandit import batch_stats, expected_score_with_stats, score_card_with_stats

_log = logging.getLogger(__name__)

_NORM_TITLE_RE = re.compile(r"[^\w一-鿿]+", flags=re.UNICODE)
_fill_lock = threading.Lock()
_filling_keys: set[tuple] = set()
_scoring_lock = threading.Lock()
_scoring_keys: set[tuple] = set()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _norm_title(s: str) -> str:
    return _NORM_TITLE_RE.sub(" ", (s or "").lower()).strip()


def _openalex_mailto() -> Optional[str]:
    import os
    return os.environ.get("UNPAYWALL_EMAIL") or None


def _reconstruct_abstract(inverted_index: Optional[dict]) -> str:
    if not inverted_index:
        return ""
    words: dict[int, str] = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words[i] for i in sorted(words))


def _openalex_work_to_meta(work: dict) -> dict:
    doi = (work.get("doi") or "").strip()
    primary = work.get("primary_location") or {}
    venue = primary.get("source") or {}
    url = (
        (primary.get("landing_page_url") or "").strip()
        or (f"https://doi.org/{doi}" if doi and not doi.startswith("http") else doi)
        or (work.get("id") or "").strip()
    )
    authors = [
        a["author"]["display_name"]
        for a in (work.get("authorships") or [])
        if a.get("author") and a["author"].get("display_name")
    ]
    return {
        "external_id": (work.get("id") or doi or "").strip(),
        "source": "openalex",
        "title": (work.get("title") or "").strip(),
        "abstract": _reconstruct_abstract(work.get("abstract_inverted_index")),
        "authors_json": authors,
        "year": work.get("publication_year"),
        "publication_date": work.get("publication_date"),
        "cited_by_count": work.get("cited_by_count"),
        "doi": doi or None,
        "url": url or None,
        "venue_name": (venue.get("display_name") or "").strip() or None,
        "source_query": work.get("_source_query") or None,
    }


def fill_explore_pool(tenant_id: int, sub_id: int, target: int = 200) -> dict:
    from explore.models import ExplorePool
    from subscriptions.models import Subscription

    try:
        sub = Subscription.objects.get(pk=sub_id, tenant_id=tenant_id)
    except Subscription.DoesNotExist:
        return {"added": 0, "existing": 0}

    current = ExplorePool.objects.filter(subscription_id=sub_id, tenant_id=tenant_id, action__isnull=True).count()
    displayable = ExplorePool.objects.filter(
        subscription_id=sub_id, tenant_id=tenant_id, action__isnull=True, scored_at__isnull=False
    ).count()
    needed = max(0, target - displayable)
    if needed <= 0:
        return {"added": 0, "existing": current}

    queries = list(sub.generated_queries or [])
    if not queries:
        return {"added": 0, "existing": current}

    existing_ids: set[str] = set()
    existing_titles: set[str] = set()
    for meta in ExplorePool.objects.filter(subscription_id=sub_id, tenant_id=tenant_id).values_list("raw_metadata_json", flat=True):
        meta = meta or {}
        eid = (meta.get("external_id") or meta.get("doi") or "").strip()
        if eid:
            existing_ids.add(eid)
        title = _norm_title(meta.get("title") or "")
        if title:
            existing_titles.add(title)

    per_query = min(200, max(10, math.ceil(target * 1.5 / len(queries))))
    since_iso = (_utcnow() - timedelta(days=1825)).date().isoformat()
    mailto = _openalex_mailto()

    def _fetch_page(c, q, page=1):
        params = {
            "filter": f"title_and_abstract.search:{q},from_publication_date:{since_iso},type:article,primary_location.source.type:journal",
            "per_page": per_query,
            "page": page,
            "select": "id,doi,title,abstract_inverted_index,authorships,publication_year,publication_date,cited_by_count,primary_location",
            "sort": "publication_date:desc",
        }
        if mailto:
            params["mailto"] = mailto
        try:
            r = c.get("https://api.openalex.org/works", params=params)
            r.raise_for_status()
            results = r.json().get("results", [])
            for work in results:
                work["_source_query"] = q
            return results
        except Exception:
            return []

    works = []
    page1_counts = {}
    with httpx.Client(timeout=20.0) as c:
        with ThreadPoolExecutor(max_workers=min(len(queries), 4)) as ex:
            futures = {q: ex.submit(_fetch_page, c, q, 1) for q in queries}
            for q, fut in futures.items():
                batch = fut.result()
                page1_counts[q] = len(batch)
                works.extend(batch)

    if len(works) < needed:
        full_queries = [q for q in queries if page1_counts.get(q, 0) >= per_query]
        if full_queries:
            with httpx.Client(timeout=20.0) as c:
                with ThreadPoolExecutor(max_workers=min(len(full_queries), 4)) as ex:
                    for batch in ex.map(lambda q: _fetch_page(c, q, 2), full_queries):
                        works.extend(batch)

    added = 0
    to_create = []
    for work in works:
        if added >= needed:
            break
        if not work.get("abstract_inverted_index"):
            continue
        meta = _openalex_work_to_meta(work)
        eid = (meta.get("external_id") or meta.get("doi") or "").strip()
        title = _norm_title(meta.get("title") or "")
        if not eid or eid in existing_ids or (title and title in existing_titles):
            continue
        to_create.append(ExplorePool(
            tenant_id=tenant_id,
            subscription_id=sub_id,
            raw_metadata_json=meta,
            external_id=eid,
        ))
        existing_ids.add(eid)
        if title:
            existing_titles.add(title)
        added += 1

    if to_create:
        ExplorePool.objects.bulk_create(to_create, ignore_conflicts=True)

    return {"added": added, "existing": current}


def get_explore_cards(tenant_id: int, sub_id: int, limit: int = 10, exclude_ids: Optional[list] = None) -> list:
    from explore.models import ExplorePool

    qs = ExplorePool.objects.filter(
        tenant_id=tenant_id,
        subscription_id=sub_id,
        action__isnull=True,
        scored_at__isnull=False,
    )
    if exclude_ids:
        qs = qs.exclude(id__in=exclude_ids)
    items = list(qs)

    all_tags: set[str] = set()
    for item in items:
        for t in (item.tags_json or []):
            all_tags.add(t)
    stats = batch_stats(tenant_id, all_tags)

    scored = [
        (score_card_with_stats(item.id, item.tags_json or [], stats), item)
        for item in items
        if item.tags_json
    ]
    scored.sort(key=lambda row: row[0], reverse=True)
    top = [item for _, item in scored[:limit]]

    result = []
    for item in top:
        meta = item.raw_metadata_json or {}
        url = meta.get("url") or ""
        if not url.lower().startswith(("http://", "https://")):
            url = ""
        result.append({
            "id": item.id,
            "title": meta.get("title") or "",
            "url": url,
            "title_zh": item.title_zh or "",
            "display_date": meta.get("publication_date") or str(meta.get("year") or ""),
            "authors": ", ".join((meta.get("authors_json") or [])[:3]),
            "cited_by_count": meta.get("cited_by_count"),
            "venue_name": meta.get("venue_name") or "",
            "tags": list(item.tags_json or [])[:4],
            "research_question": item.research_question or "",
            "methodology": item.methodology or "",
            "key_findings": list(item.key_findings_json or []),
            "llm_reason": item.llm_reason or "",
            "llm_pending": item.scored_at is None,
            "bandit_score": expected_score_with_stats(item.tags_json or [], stats),
            "action": item.action,
        })
    return result


def record_explore_action(tenant_id: int, pool_id: int, action: str) -> dict:
    if action not in {"saved", "skipped", "passed"}:
        raise ValueError("invalid action")
    from explore.models import ExplorePool
    try:
        item = ExplorePool.objects.get(pk=pool_id, tenant_id=tenant_id)
    except ExplorePool.DoesNotExist:
        raise ValueError("not found")

    if item.action == action:
        return {"pool_id": item.id, "action": action, "changed": False}

    item.action = action
    item.acted_at = _utcnow()
    item.save(update_fields=["action", "acted_at"])

    from explore.bandit import apply_action
    apply_action(tenant_id, item.tags_json or [], action)

    return {"pool_id": item.id, "action": action, "changed": True}


def invalidate_query_cache(tenant_id: int, sub_id: int) -> None:
    """Called after subscription description changes; drops unscored pool items."""
    from explore.models import ExplorePool
    ExplorePool.objects.filter(
        tenant_id=tenant_id, subscription_id=sub_id, scored_at__isnull=True
    ).delete()
