"""reference_fetcher.py — 共享引用数据抓取模块。

提供两个方向的论文引用查询（均按 DOI 查询）：
  fetch_cited_by(doi, limit)   → 谁引用了这篇（前向）
  fetch_references(doi, limit) → 这篇引用了谁（后向）

双源：Semantic Scholar + OpenAlex，结果按 DOI 去重合并。
字段：doi / title / year / authors / abstract / source

设计意图：供 ForwardTrackService、BackwardTrackService、SubscriptionService 共同导入，
不含缓存逻辑（缓存在各自 Service 中维护）。
"""
from __future__ import annotations

import logging
import re
import threading
import time
import functools
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Iterable, Optional

import httpx

from ._paths import ensure_scripts_on_path

_log = logging.getLogger(__name__)

_SS_BASE = "https://api.semanticscholar.org/graph/v1"
_OPENALEX_BASE = "https://api.openalex.org"
_TIMEOUT = 30
_PER_PAGE = 100

# SS 免费配额 100 req/5min；1 req/s 节流，多线程共享
_SS_INTERVAL = 1.0
_SS_LOCK = threading.Lock()
_ss_last_call: float = 0.0

_DOI_ALLOWED = re.compile(r"^10\.[0-9]{1,9}/[A-Za-z0-9._;()/:\-]+$")


# ─── 数据结构 ────────────────────────────────────────────────────────────────

@dataclass
class ReferenceItem:
    doi: str
    title: str
    year: Optional[int]
    authors: str
    abstract: str
    source: str  # "ss" | "openalex" | "both"


# ─── DOI 工具 ────────────────────────────────────────────────────────────────

def normalize_doi(doi: str) -> str:
    """归一化 DOI：剥前缀、转小写、校验字符集。不符合规范返回空串。"""
    d = (doi or "").strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.lower().startswith(prefix):
            d = d[len(prefix):]
            break
    d = d.lower()
    if not d:
        return ""
    if not _DOI_ALLOWED.match(d):
        return ""
    if ".." in d:
        return ""
    return d


# ─── HTTP 工具 ───────────────────────────────────────────────────────────────

def _ss_get(url: str, params: dict, headers: dict) -> Optional[httpx.Response]:
    """SS GET 限速器：节流到 _SS_INTERVAL，遇 429 退避一次重试。
    锁只保护时间戳读写，sleep 和 HTTP 调用在锁外执行，避免长时间持锁阻塞其他线程。
    """
    global _ss_last_call
    with _SS_LOCK:
        now = time.time()
        elapsed = now - _ss_last_call
        if elapsed < _SS_INTERVAL:
            # 预约下一个时间槽
            _ss_last_call += _SS_INTERVAL
            sleep_time = _ss_last_call - now
        else:
            _ss_last_call = now
            sleep_time = 0.0

    # sleep 和 HTTP 在锁外执行
    if sleep_time > 0:
        time.sleep(sleep_time)

    for attempt in (0, 1):
        if attempt:
            time.sleep(5.0)
        try:
            resp = httpx.get(url, params=params, headers=headers, timeout=_TIMEOUT)
        except Exception as e:
            _log.warning("[ss] http error: %s", e)
            return None
        if resp.status_code != 429:
            return resp
        _log.warning("[ss] 429 rate-limited; backing off")
    return None


@functools.lru_cache(maxsize=1)
def _ss_headers() -> dict:
    ensure_scripts_on_path()
    try:
        from config import SS_API_KEY  # type: ignore
        return {"x-api-key": SS_API_KEY} if SS_API_KEY else {}
    except Exception:
        return {}


@functools.lru_cache(maxsize=1)
def _openalex_mailto() -> Optional[str]:
    ensure_scripts_on_path()
    try:
        from config import UNPAYWALL_EMAIL  # type: ignore
        return UNPAYWALL_EMAIL or None
    except Exception:
        return None


# ─── 字段辅助 ────────────────────────────────────────────────────────────────

def _reconstruct_abstract(inverted_index: Optional[dict]) -> str:
    """把 OpenAlex abstract_inverted_index 还原成正文。"""
    if not inverted_index:
        return ""
    words: dict[int, str] = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words[i] for i in sorted(words))


def _ss_item(data: dict, source: str) -> ReferenceItem:
    ext = data.get("externalIds") or {}
    authors = ", ".join(
        (a.get("name") or "") for a in (data.get("authors") or [])[:3]
    )
    return ReferenceItem(
        doi=normalize_doi(ext.get("DOI", "") or ""),
        title=(data.get("title") or "").strip(),
        year=data.get("year"),
        authors=authors,
        abstract=(data.get("abstract") or "").strip(),
        source=source,
    )


def _oa_item(w: dict) -> ReferenceItem:
    return ReferenceItem(
        doi=normalize_doi((w.get("doi") or "")),
        title=(w.get("title") or "").strip(),
        year=w.get("publication_year"),
        authors=", ".join(
            (a.get("author") or {}).get("display_name", "")
            for a in (w.get("authorships") or [])[:3]
        ),
        abstract=_reconstruct_abstract(w.get("abstract_inverted_index")),
        source="openalex",
    )


_SS_FIELDS = "title,year,authors,externalIds,abstract"
_OA_SELECT = "title,doi,publication_year,authorships,abstract_inverted_index"


# ─── 前向抓取：谁引用了这篇 ─────────────────────────────────────────────────

def _ss_cited_by(doi: str, limit: int) -> list[ReferenceItem]:
    try:
        resp = _ss_get(
            f"{_SS_BASE}/paper/DOI:{doi}/citations",
            {"fields": _SS_FIELDS, "limit": min(limit, _PER_PAGE)},
            _ss_headers(),
        )
        if resp is None or resp.status_code != 200:
            _log.warning("[ss] cited_by %s: HTTP %s", doi, "n/a" if resp is None else resp.status_code)
            return []
        _data = resp.json().get("data")
        return [
            _ss_item(entry.get("citingPaper") or {}, "ss")
            for entry in (_data if _data is not None else [])
            if entry.get("citingPaper")
        ]
    except Exception as e:
        _log.warning("[ss] cited_by %s: %s", doi, e)
        return []


def _oa_cited_by(doi: str, limit: int) -> list[ReferenceItem]:
    try:
        mailto = _openalex_mailto()
        p: dict = {"mailto": mailto} if mailto else {}
        r1 = httpx.get(f"{_OPENALEX_BASE}/works/doi:{doi}", params=p, timeout=_TIMEOUT)
        if r1.status_code != 200:
            return []
        work_id = (r1.json().get("id") or "").rsplit("/", 1)[-1]
        if not work_id:
            return []
        p2: dict = {
            "filter": f"cites:{work_id}",
            "select": _OA_SELECT,
            "per-page": min(limit, _PER_PAGE),
        }
        if mailto:
            p2["mailto"] = mailto
        r2 = httpx.get(f"{_OPENALEX_BASE}/works", params=p2, timeout=_TIMEOUT)
        if r2.status_code != 200:
            return []
        return [_oa_item(w) for w in r2.json().get("results", [])]
    except Exception as e:
        _log.warning("[openalex] cited_by %s: %s", doi, e)
        return []


# ─── 后向抓取：这篇引用了谁 ─────────────────────────────────────────────────

def _ss_references(doi: str, limit: int) -> list[ReferenceItem]:
    try:
        resp = _ss_get(
            f"{_SS_BASE}/paper/DOI:{doi}/references",
            {"fields": _SS_FIELDS, "limit": min(limit, _PER_PAGE)},
            _ss_headers(),
        )
        if resp is None or resp.status_code != 200:
            _log.warning("[ss] references %s: HTTP %s", doi, "n/a" if resp is None else resp.status_code)
            return []
        _data = resp.json().get("data")
        return [
            _ss_item(entry.get("citedPaper") or {}, "ss")
            for entry in (_data if _data is not None else [])
            if entry.get("citedPaper")
        ]
    except Exception as e:
        _log.warning("[ss] references %s: %s", doi, e)
        return []


_OA_ID_RE = re.compile(r"^W\d+$")


def _oa_references(doi: str, limit: int) -> list[ReferenceItem]:
    """OpenAlex 后向：先取 referenced_works ID 列表，再并行批量查详情。"""
    try:
        mailto = _openalex_mailto()
        p: dict = {"mailto": mailto} if mailto else {}
        r1 = httpx.get(f"{_OPENALEX_BASE}/works/doi:{doi}", params=p, timeout=_TIMEOUT)
        if r1.status_code != 200:
            return []
        # 白名单校验 ID 格式（^W\d+$），防止外部 API 响应注入 filter 参数
        ref_ids = [
            rid.rsplit("/", 1)[-1]
            for rid in (r1.json().get("referenced_works") or [])
            if rid
        ]
        ref_ids = [rid for rid in ref_ids if _OA_ID_RE.match(rid)][:limit]
        if not ref_ids:
            return []

        def _fetch_batch(batch: list[str]) -> list[ReferenceItem]:
            p2: dict = {
                "filter": f"ids.openalex:{'|'.join(batch)}",
                "select": _OA_SELECT,
                "per-page": len(batch),
            }
            if mailto:
                p2["mailto"] = mailto
            r2 = httpx.get(f"{_OPENALEX_BASE}/works", params=p2, timeout=_TIMEOUT)
            if r2.status_code == 200:
                return [_oa_item(w) for w in r2.json().get("results", [])]
            return []

        batches = [ref_ids[i:i + 50] for i in range(0, len(ref_ids), 50)]
        results: list[ReferenceItem] = []
        # 并行发批，最多 4 个并发（OpenAlex 无明确速率限制，保守起见限 4）
        with ThreadPoolExecutor(max_workers=min(4, len(batches))) as ex:
            for items in ex.map(_fetch_batch, batches):
                results.extend(items)
        return results
    except Exception as e:
        _log.warning("[openalex] references %s: %s", doi, e)
        return []


# ─── 去重合并 ────────────────────────────────────────────────────────────────

def merge_dedup(*lists: Iterable[ReferenceItem]) -> list[ReferenceItem]:
    """按 DOI 优先去重，无 DOI 按 (title.lower(), year) 兜底。两源同时命中改 source='both'。"""
    by_doi: dict[str, ReferenceItem] = {}
    by_titleyear: dict[tuple, ReferenceItem] = {}
    order: list[ReferenceItem] = []

    def _merge_into(existing: ReferenceItem, new: ReferenceItem) -> None:
        if len(new.title) > len(existing.title):
            existing.title = new.title
        if not existing.authors and new.authors:
            existing.authors = new.authors
        if existing.year is None and new.year is not None:
            existing.year = new.year
        if not existing.abstract and new.abstract:
            existing.abstract = new.abstract
        if existing.source != new.source:
            existing.source = "both"

    for lst in lists:
        for item in lst:
            doi = item.doi
            key_t = (item.title.strip().lower(), item.year)
            if doi:
                if doi in by_doi:
                    _merge_into(by_doi[doi], item)
                else:
                    by_doi[doi] = item
                    order.append(item)
            elif key_t[0]:
                if key_t in by_titleyear:
                    _merge_into(by_titleyear[key_t], item)
                else:
                    by_titleyear[key_t] = item
                    order.append(item)
            # 既无 DOI 也无 title 的条目直接丢弃
    return order


# ─── 公开 API ────────────────────────────────────────────────────────────────

def fetch_cited_by(doi: str, limit: int = 100) -> list[ReferenceItem]:
    """前向：查谁引用了这篇论文。返回 ReferenceItem 列表，已去重合并。"""
    doi_norm = normalize_doi(doi)
    if not doi_norm:
        raise ValueError("invalid doi")
    return merge_dedup(_ss_cited_by(doi_norm, limit), _oa_cited_by(doi_norm, limit))


def fetch_references(doi: str, limit: int = 100) -> list[ReferenceItem]:
    """后向：查这篇论文引用了哪些论文。返回 ReferenceItem 列表，已去重合并。"""
    doi_norm = normalize_doi(doi)
    if not doi_norm:
        raise ValueError("invalid doi")
    return merge_dedup(_ss_references(doi_norm, limit), _oa_references(doi_norm, limit))
