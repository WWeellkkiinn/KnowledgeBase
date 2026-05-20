"""Journal service: seed bootstrap, lookup, OpenAlex fetch, paper attach.

Ported from services/journal_service.py — same algorithm, Django ORM.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from django.db import IntegrityError

from .models import Journal

_log = logging.getLogger(__name__)

SEED_PATH = Path(__file__).resolve().parent / "seed" / "journals.json"
_OPENALEX_BASE = "https://api.openalex.org"
_TIMEOUT = 30
_ISSN_RE = re.compile(r"^\d{4}-\d{3}[\dXx]$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_issn(issn: str) -> str:
    s = (issn or "").strip()
    if _ISSN_RE.match(s):
        return s[:-1] + s[-1].upper()
    return s


def _make_surrogate_issn(name: str) -> str:
    digest = hashlib.sha1((name or "").lower().encode()).hexdigest()[:10]
    return f"u:{digest}"


def _normalize_name(name: str) -> str:
    n = (name or "").lower()
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


# ─── name cache ────────────────────────────────────────────────────────────────

_name_cache: dict[str, int] = {}
_name_cache_loaded: bool = False
_name_cache_lock = threading.Lock()


def _ensure_name_cache() -> None:
    global _name_cache_loaded
    if _name_cache_loaded:
        return
    with _name_cache_lock:
        if _name_cache_loaded:
            return
        for j in Journal.objects.only("id", "name"):
            key = _normalize_name(j.name or "")
            if key:
                _name_cache.setdefault(key, j.id)
        _name_cache_loaded = True


def _cache_journal_name(name: str, journal_id: int) -> None:
    key = _normalize_name(name or "")
    if not key:
        return
    with _name_cache_lock:
        _name_cache[key] = journal_id


def _reset_name_cache() -> None:
    global _name_cache_loaded
    with _name_cache_lock:
        _name_cache.clear()
        _name_cache_loaded = False


# ─── OpenAlex ──────────────────────────────────────────────────────────────────


def _openalex_mailto() -> Optional[str]:
    import os
    return os.environ.get("UNPAYWALL_EMAIL") or None


def fetch_journal_from_doi(doi: str) -> Optional[dict]:
    if not doi:
        return None
    mailto = _openalex_mailto()
    params = {"mailto": mailto} if mailto else {}
    try:
        resp = httpx.get(f"{_OPENALEX_BASE}/works/doi:{doi}", params=params, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception as e:
        _log.warning("[journal] openalex %s failed: %s", doi, e)
        return None
    src = ((data.get("primary_location") or {}).get("source")) or (data.get("host_venue") or None)
    if not src:
        return None
    issns = src.get("issn") or []
    issn = src.get("issn_l") or (issns[0] if issns else "")
    name = (src.get("display_name") or "").strip()
    if not issn and not name:
        return None
    return {
        "issn": _normalize_issn(issn),
        "name": name,
        "publisher": src.get("host_organization_name") or None,
        "oa_status": (data.get("open_access") or {}).get("oa_status") or None,
        "source_dataset": "openalex",
    }


# ─── Lookup ────────────────────────────────────────────────────────────────────


def lookup_by_issn(issn: str) -> Optional[Journal]:
    issn_norm = _normalize_issn(issn)
    if not issn_norm:
        return None
    return Journal.objects.filter(issn=issn_norm).first()


def lookup_by_name(name: str) -> Optional[Journal]:
    n = _normalize_name(name)
    if not n:
        return None
    _ensure_name_cache()
    jid = _name_cache.get(n)
    if jid is None:
        return None
    return Journal.objects.filter(pk=jid).first()


# ─── Seed bootstrap ────────────────────────────────────────────────────────────


def bootstrap_from_seed(seed_path: Path = SEED_PATH) -> dict:
    """Upsert journals from seed JSON. Returns {inserted, updated, skipped}."""
    try:
        raw = seed_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        _log.warning("[journal] seed not found: %s", seed_path)
        return {"inserted": 0, "updated": 0, "skipped": 0}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        _log.error("[journal] seed JSON invalid: %s", e)
        return {"inserted": 0, "updated": 0, "skipped": 0}
    if not isinstance(data, list):
        return {"inserted": 0, "updated": 0, "skipped": 0}

    existing_by_issn = {j.issn: j for j in Journal.objects.all()}
    inserted = updated = skipped = 0
    for row in data:
        if not isinstance(row, dict):
            skipped += 1
            continue
        issn = _normalize_issn(str(row.get("issn", "") or ""))
        name = str(row.get("name", "") or "").strip()
        if not issn or not name:
            skipped += 1
            continue
        tier = row.get("quality_tier")
        if tier is not None and (not isinstance(tier, int) or tier < 1 or tier > 4):
            tier = None
        publisher = row.get("publisher") if isinstance(row.get("publisher"), str) else None
        oa_status = row.get("oa_status") if isinstance(row.get("oa_status"), str) else None
        source_dataset = row.get("source_dataset", "manual")
        if not isinstance(source_dataset, str):
            source_dataset = "manual"

        existing = existing_by_issn.get(issn)
        if existing is None:
            j = Journal.objects.create(
                issn=issn, name=name, publisher=publisher,
                quality_tier=tier,
                is_predatory=bool(row.get("is_predatory", False)),
                oa_status=oa_status, source_dataset=source_dataset,
                refreshed_at=_utcnow(),
            )
            _cache_journal_name(name, j.pk)
            inserted += 1
        else:
            existing.name = name
            if publisher:
                existing.publisher = publisher
            if tier is not None:
                existing.quality_tier = tier
            existing.is_predatory = bool(row.get("is_predatory", existing.is_predatory))
            if oa_status:
                existing.oa_status = oa_status
            existing.source_dataset = source_dataset
            existing.refreshed_at = _utcnow()
            existing.save()
            updated += 1
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


# ─── Attach to paper ───────────────────────────────────────────────────────────


def attach_journal_to_paper(paper, meta: Optional[dict] = None) -> Optional[Journal]:
    """Link a Paper (Django model) to a Journal, creating one if needed."""
    if meta is None:
        meta = fetch_journal_from_doi(paper.doi or "")
    if not meta:
        return None
    issn = _normalize_issn(meta.get("issn", ""))
    name = (meta.get("name") or "").strip()

    journal: Optional[Journal] = None
    if issn:
        journal = lookup_by_issn(issn)
    if journal is None and name:
        journal = lookup_by_name(name)

    if journal is None:
        if not issn and not name:
            return None
        surrogate = issn or _make_surrogate_issn(name)
        try:
            journal = Journal.objects.create(
                issn=surrogate, name=name or "(unknown)",
                publisher=meta.get("publisher"),
                quality_tier=meta.get("quality_tier"),
                is_predatory=bool(meta.get("is_predatory", False)),
                oa_status=meta.get("oa_status"),
                source_dataset=meta.get("source_dataset", "openalex"),
                refreshed_at=_utcnow(),
            )
        except IntegrityError:
            journal = Journal.objects.filter(issn=surrogate).first()
            if journal is None:
                raise
        if journal is not None:
            _cache_journal_name(journal.name or name, journal.pk)
    else:
        updates = []
        if journal.quality_tier is None and meta.get("quality_tier") is not None:
            journal.quality_tier = meta["quality_tier"]
            updates.append("quality_tier")
        if not journal.oa_status and meta.get("oa_status"):
            journal.oa_status = meta["oa_status"]
            updates.append("oa_status")
        if not journal.publisher and meta.get("publisher"):
            journal.publisher = meta["publisher"]
            updates.append("publisher")
        if updates:
            journal.save(update_fields=updates)

    paper.journal_id = journal.pk
    paper.save(update_fields=["journal_id"])
    return journal
