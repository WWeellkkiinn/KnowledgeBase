"""EasyScholar journal rank query service.

Ported from services/easyscholar_service.py — same algorithm, same external API.
SQLAlchemy session calls replaced with Django ORM.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

_log = logging.getLogger(__name__)

_API_URL = "https://www.easyscholar.cc/open/getPublicationRank"
_CACHE_TTL_DAYS = 180
_RATE_INTERVAL = 0.5


class _KeyPool:
    """Per-key rate-limited pool. Always picks the key whose next slot is soonest."""

    def __init__(self, keys: list[str], interval: float) -> None:
        self._keys = keys
        self._last = [0.0] * len(keys)
        self._lock = threading.Lock()
        self._interval = interval

    def acquire(self) -> tuple[str, float]:
        with self._lock:
            now = time.time()
            idx = min(range(len(self._keys)), key=lambda i: self._last[i])
            next_avail = self._last[idx] + self._interval
            sleep_time = max(0.0, next_avail - now)
            self._last[idx] = max(now, next_avail)
        return self._keys[idx], sleep_time


def _load_es_pool() -> _KeyPool:
    raw = os.environ.get("EASYSCHOLAR_SECRET_KEY", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()] or [""]
    _log.info("[easyscholar] %d key(s) loaded", len(keys))
    return _KeyPool(keys, _RATE_INTERVAL)


_es_pool: _KeyPool = _load_es_pool()

DISPLAY_FIELDS: list[tuple[str, str]] = [
    ("sci", "SCI"),
    ("ssci", "SSCI"),
    ("sciif", "IF"),
    ("sciUp", "中科院"),
    ("sciUpTop", "Top"),
    ("ccf", "CCF"),
    ("cssci", "CSSCI"),
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_stale(fetched_at: Optional[datetime]) -> bool:
    if fetched_at is None:
        return True
    return _utcnow() - fetched_at > timedelta(days=_CACHE_TTL_DAYS)


def fetch_from_api(journal_name: str) -> Optional[dict]:
    """Call EasyScholar API; return officialRank.all dict or None on failure."""
    key, sleep_time = _es_pool.acquire()
    if not key:
        _log.warning("[easyscholar] EASYSCHOLAR_SECRET_KEY not set")
        return None
    if sleep_time > 0:
        time.sleep(sleep_time)
    encoded = urllib.parse.quote(journal_name, safe="")
    try:
        resp = httpx.get(
            f"{_API_URL}?secretKey={key}&publicationName={encoded}",
            timeout=15,
        )
        if resp.status_code != 200:
            _log.warning("[easyscholar] HTTP %s for %s", resp.status_code, journal_name)
            return None
        data = resp.json()
        if data.get("code") != 200:
            _log.warning("[easyscholar] API error %s: %s", data.get("code"), data.get("msg"))
            return None
        return (data.get("data") or {}).get("officialRank", {}).get("all") or {}
    except Exception as exc:
        _log.warning("[easyscholar] request failed for %s: %s", journal_name, exc)
        return None


def get_or_fetch(journal) -> Optional[dict]:
    """Return cached easyscholar_json or refresh from API, saving to journal row."""
    if not _is_stale(journal.easyscholar_fetched_at):
        return journal.easyscholar_json
    result = fetch_from_api(journal.name)
    journal.easyscholar_json = result
    journal.easyscholar_fetched_at = _utcnow()
    try:
        journal.save(update_fields=["easyscholar_json", "easyscholar_fetched_at"])
    except Exception as exc:
        _log.warning("[easyscholar] save failed: %s", exc)
    return result


def extract_badges(raw: Optional[dict]) -> list[dict]:
    if not raw:
        return []
    badges = []
    for field, label in DISPLAY_FIELDS:
        val = raw.get(field)
        if val:
            badges.append({"label": label, "value": str(val)})
    return badges
