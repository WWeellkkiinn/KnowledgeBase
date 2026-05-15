"""ForwardTrackService — 前向追踪（谁引用了这篇论文）。

共享逻辑在 _track_base._BaseTrackService，此处只声明差异部分。
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from database import models
from .reference_fetcher import (
    ReferenceItem,
    _oa_cited_by,
    _ss_cited_by,
    merge_dedup,
    normalize_doi as _normalize_doi,
)
from ._track_base import _BaseTrackService, _utcnow

_log = logging.getLogger(__name__)

# 向后兼容：测试直接从此模块导入
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
    _cache_model = models.ForwardTrackCache
    _papers_key = "citing_papers"
    _count_key = "citing_count"
    _direction = "forward"

    def _fetch(self, doi: str, limit: Optional[int]) -> list[ReferenceItem]:
        ss_raw: list[dict] = []
        oa_raw: list[dict] = []
        try:
            ss_raw = self._fetch_ss(doi, limit)
        except Exception as exc:
            _log.warning("ForwardTrackService _fetch_ss failed doi=%s: %s", doi, exc)
        try:
            oa_raw = self._fetch_openalex(doi, limit)
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

    @staticmethod
    def _merge(*lists: list[dict]) -> list[dict]:
        """向后兼容 shim：接受 dict 列表，返回 dict 列表。"""
        items_per_src = [[_dict_to_item(d) for d in lst] for lst in lists]
        return [_item_to_dict(r) for r in merge_dedup(*items_per_src)]
