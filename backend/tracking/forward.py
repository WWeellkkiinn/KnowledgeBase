"""ForwardTrackService — who cites this paper.

Ported from services/forward_track_service.py.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Optional

from .base import _BaseTrackService
from .fetcher import ReferenceItem, _oa_cited_by, _ss_cited_by, merge_dedup

_log = logging.getLogger(__name__)

_CACHE_TTL = timedelta(days=7)


def _item_to_dict(r: ReferenceItem) -> dict:
    return {
        "doi": r.doi, "title": r.title, "year": r.year,
        "authors": r.authors, "abstract": r.abstract,
        "source": r.source, "venue_name": r.venue_name,
        "venue_issn": r.venue_issn,
    }


def _dict_to_item(d: dict) -> ReferenceItem:
    if isinstance(d, ReferenceItem):
        return d
    return ReferenceItem(
        doi=d.get("doi", ""),
        title=d.get("title", ""),
        year=d.get("year"),
        authors=d.get("authors", ""),
        abstract=d.get("abstract", ""),
        source=d.get("source", "ss"),
        venue_name=d.get("venue_name", ""),
        venue_issn=d.get("venue_issn", ""),
    )


class ForwardTrackService(_BaseTrackService):
    _cache_model_name = "tracking.ForwardTrackCache"
    _papers_key = "citing_papers"
    _count_key = "citing_count"
    _direction = "forward"
    _cache_ttl = _CACHE_TTL

    def _fetch(self, doi: str, limit: Optional[int]) -> list[ReferenceItem]:
        ss_raw: list[dict] = []
        oa_raw: list[dict] = []
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_ss = ex.submit(self._fetch_ss, doi, limit)
            f_oa = ex.submit(self._fetch_openalex, doi, limit)
            try:
                ss_raw = f_ss.result()
            except Exception as exc:
                _log.warning("ForwardTrackService _fetch_ss failed doi=%s: %s", doi, exc)
            try:
                oa_raw = f_oa.result()
            except Exception as exc:
                _log.warning("ForwardTrackService _fetch_openalex failed doi=%s: %s", doi, exc)
        return merge_dedup(
            [_dict_to_item(d) for d in ss_raw],
            [_dict_to_item(d) for d in oa_raw],
        )

    def _fetch_ss(self, doi: str, limit: Optional[int]) -> list[dict]:
        return [_item_to_dict(r) for r in _ss_cited_by(doi, limit)]

    def _fetch_openalex(self, doi: str, limit: Optional[int]) -> list[dict]:
        return [_item_to_dict(r) for r in _oa_cited_by(doi, limit)]
