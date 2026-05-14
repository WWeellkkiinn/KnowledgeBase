"""BackwardTrackService — 后向追踪（这篇论文引用了哪些论文）。

共享逻辑在 _track_base._BaseTrackService，此处只声明差异部分。
"""
from __future__ import annotations

from database import models
from .reference_fetcher import fetch_references
from ._track_base import _BaseTrackService


class BackwardTrackService(_BaseTrackService):
    _cache_model = models.BackwardTrackCache
    _papers_key = "referenced_papers"
    _count_key = "references_count"
    _direction = "backward"

    def _fetch(self, doi: str, limit: int) -> list:
        return fetch_references(doi, limit)
