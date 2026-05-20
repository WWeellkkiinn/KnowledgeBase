"""doi_resolver.py — 根据论文标题查询 DOI。

双源策略：Semantic Scholar 优先（字段全、速度快），CrossRef 兜底。
标题相似度用简单词集 Jaccard，阈值 0.6（宽松但足以过滤离题结果）。
每次调用最多耗时 ~10s（两个 API 各 5s timeout）。
"""
from __future__ import annotations

import functools
import logging
import re
from typing import Optional

import httpx

_log = logging.getLogger(__name__)
_SS_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
_CR_WORKS = "https://api.crossref.org/works"
_TIMEOUT = 8


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _similarity(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


@functools.lru_cache(maxsize=512)
def resolve_doi(title: str) -> Optional[str]:
    """按标题查询 DOI。结果缓存避免重复请求。找不到或置信度低时返回 None。"""
    if not title or not title.strip():
        return None
    doi = _try_semantic_scholar(title) or _try_crossref(title)
    if doi:
        _log.info("[doi_resolver] resolved: %s → %s", title[:60], doi)
    return doi


def _try_semantic_scholar(title: str) -> Optional[str]:
    try:
        resp = httpx.get(
            _SS_SEARCH,
            params={"query": title, "fields": "externalIds,title", "limit": 3},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        for paper in (resp.json().get("data") or []):
            t = paper.get("title") or ""
            doi = (paper.get("externalIds") or {}).get("DOI")
            if doi and _similarity(t, title) >= 0.75:
                return doi
    except Exception as exc:
        _log.debug("[doi_resolver] SS failed: %s", exc)
    return None


def _try_crossref(title: str) -> Optional[str]:
    try:
        resp = httpx.get(
            _CR_WORKS,
            params={"query.title": title, "rows": 3, "select": "DOI,title"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        for item in (resp.json().get("message", {}).get("items") or []):
            titles = item.get("title") or []
            t = titles[0] if titles else ""
            doi = item.get("DOI")
            if doi and _similarity(t, title) >= 0.75:
                return doi
    except Exception as exc:
        _log.debug("[doi_resolver] CrossRef failed: %s", exc)
    return None
