"""BackwardTrackService — what this paper cites.

Ported from services/backward_track_service.py.
"""
from __future__ import annotations

from typing import Optional

from .base import _BaseTrackService
from .fetcher import fetch_references


class BackwardTrackService(_BaseTrackService):
    _cache_model_name = "tracking.BackwardTrackCache"
    _papers_key = "referenced_papers"
    _count_key = "references_count"
    _direction = "backward"
    _cache_ttl = None  # references don't change after publication

    def _fetch(self, doi: str, limit: Optional[int]) -> list:
        return fetch_references(doi, limit)
