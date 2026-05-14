"""ForwardTrackService — 前向追踪（谁引用了这篇论文）。

共享逻辑在 _track_base._BaseTrackService，此处只声明差异部分。
"""
from __future__ import annotations

from database import models
from .reference_fetcher import fetch_cited_by
from ._track_base import _BaseTrackService


class ForwardTrackService(_BaseTrackService):
    _cache_model = models.ForwardTrackCache
    _papers_key = "citing_papers"
    _count_key = "citing_count"
    _direction = "forward"

    def _fetch(self, doi: str, limit: int) -> list:
        return fetch_cited_by(doi, limit)
