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

# SS API key 认证后限速 1 req/s（官方值），实测 0.8s 无 429，更快
_SS_INTERVAL = 0.8
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
    venue_name: str = ""
    venue_issn: str = ""


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
    venue = data.get("publicationVenue") or data.get("journal") or {}
    issn_raw = venue.get("issn")
    if isinstance(issn_raw, list):
        venue_issn = issn_raw[0] if issn_raw else ""
    elif isinstance(issn_raw, str):
        venue_issn = issn_raw
    else:
        venue_issn = ""
    return ReferenceItem(
        doi=normalize_doi(ext.get("DOI", "") or ""),
        title=(data.get("title") or "").strip(),
        year=data.get("year"),
        authors=authors,
        abstract=(data.get("abstract") or "").strip(),
        source=source,
        venue_name=(venue.get("name") or "").strip(),
        venue_issn=venue_issn,
    )


def _oa_item(w: dict) -> ReferenceItem:
    src = ((w.get("primary_location") or {}).get("source")) or {}
    issns = src.get("issn") or []
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
        venue_name=(src.get("display_name") or "").strip(),
        venue_issn=(src.get("issn_l") or (issns[0] if issns else "")),
    )


_SS_FIELDS = "title,year,authors,externalIds,abstract,journal,publicationVenue"
_OA_SELECT = "title,doi,publication_year,authorships,abstract_inverted_index,primary_location"


# ─── 前向抓取：谁引用了这篇 ─────────────────────────────────────────────────

def _ss_cited_by(doi: str, limit: Optional[int] = None) -> list[ReferenceItem]:
    try:
        results: list[ReferenceItem] = []
        offset = 0
        while True:
            page_size = _PER_PAGE if limit is None else min(_PER_PAGE, limit - len(results))
            if page_size <= 0:
                break
            resp = _ss_get(
                f"{_SS_BASE}/paper/DOI:{doi}/citations",
                {"fields": _SS_FIELDS, "limit": page_size, "offset": offset},
                _ss_headers(),
            )
            if resp is None or resp.status_code != 200:
                _log.warning("[ss] cited_by %s: HTTP %s", doi, "n/a" if resp is None else resp.status_code)
                return results
            _data = resp.json().get("data") or []
            batch = [
                _ss_item(entry.get("citingPaper") or {}, "ss")
                for entry in _data
                if entry.get("citingPaper")
            ]
            results.extend(batch)
            # 用原始响应条目数判断是否到末页，避免 null 过滤导致提前退出
            if len(_data) < page_size or (limit is not None and len(results) >= limit):
                break
            offset += _PER_PAGE
        return results
    except Exception as e:
        _log.warning("[ss] cited_by %s: %s", doi, e)
        return []


def _oa_cited_by(doi: str, limit: Optional[int] = None) -> list[ReferenceItem]:
    try:
        mailto = _openalex_mailto()
        p: dict = {"mailto": mailto} if mailto else {}
        r1 = httpx.get(f"{_OPENALEX_BASE}/works/doi:{doi}", params=p, timeout=_TIMEOUT)
        if r1.status_code != 200:
            return []
        work_id = (r1.json().get("id") or "").rsplit("/", 1)[-1]
        if not work_id:
            return []
        results: list[ReferenceItem] = []
        cursor: Optional[str] = "*"
        while cursor:
            page_size = _PER_PAGE if limit is None else min(_PER_PAGE, limit - len(results))
            if page_size <= 0:
                break
            p2: dict = {
                "filter": f"cites:{work_id}",
                "select": _OA_SELECT,
                "per-page": page_size,
                "cursor": cursor,
            }
            if mailto:
                p2["mailto"] = mailto
            r2 = httpx.get(f"{_OPENALEX_BASE}/works", params=p2, timeout=_TIMEOUT)
            if r2.status_code != 200:
                return results
            data = r2.json()
            results.extend(_oa_item(w) for w in data.get("results", []))
            cursor = (data.get("meta") or {}).get("next_cursor")
            if limit is not None and len(results) >= limit:
                break
        return results
    except Exception as e:
        _log.warning("[openalex] cited_by %s: %s", doi, e)
        return []


# ─── 后向抓取：这篇引用了谁 ─────────────────────────────────────────────────

def _ss_references(doi: str, limit: Optional[int] = None) -> list[ReferenceItem]:
    try:
        results: list[ReferenceItem] = []
        offset = 0
        while True:
            page_size = _PER_PAGE if limit is None else min(_PER_PAGE, limit - len(results))
            if page_size <= 0:
                break
            resp = _ss_get(
                f"{_SS_BASE}/paper/DOI:{doi}/references",
                {"fields": _SS_FIELDS, "limit": page_size, "offset": offset},
                _ss_headers(),
            )
            if resp is None or resp.status_code != 200:
                _log.warning("[ss] references %s: HTTP %s", doi, "n/a" if resp is None else resp.status_code)
                return results
            _data = resp.json().get("data") or []
            batch = [
                _ss_item(entry.get("citedPaper") or {}, "ss")
                for entry in _data
                if entry.get("citedPaper")
            ]
            results.extend(batch)
            if len(_data) < page_size or (limit is not None and len(results) >= limit):
                break
            offset += _PER_PAGE
        return results
    except Exception as e:
        _log.warning("[ss] references %s: %s", doi, e)
        return []


_OA_ID_RE = re.compile(r"^W\d+$")
_CR_WORKS = "https://api.crossref.org/works"


def _cr_references(doi: str, limit: Optional[int] = None) -> list[ReferenceItem]:
    """Crossref 后向：一次请求拿到完整参考文献列表，polite pool 无实际限速。"""
    try:
        mailto = _openalex_mailto()  # 复用同一邮箱进 polite pool
        p: dict = {"mailto": mailto} if mailto else {}
        resp = httpx.get(f"{_CR_WORKS}/{doi}", params=p, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return []
        refs = (resp.json().get("message") or {}).get("reference") or []
        if limit is not None:
            refs = refs[:limit]
        results: list[ReferenceItem] = []
        for r in refs:
            raw_doi = r.get("DOI") or ""
            title = (r.get("article-title") or r.get("volume-title") or "").strip()
            year_raw = r.get("year")
            try:
                year: Optional[int] = int(year_raw) if year_raw else None
            except (ValueError, TypeError):
                year = None
            author = (r.get("author") or "").strip()
            journal = (r.get("journal-title") or r.get("series-title") or "").strip()
            results.append(ReferenceItem(
                doi=normalize_doi(raw_doi),
                title=title,
                year=year,
                authors=author,
                abstract="",
                source="crossref",
                venue_name=journal,
            ))
        return [r for r in results if r.doi or r.title]
    except Exception as e:
        _log.warning("[crossref] references %s: %s", doi, e)
        return []


def _oa_references(doi: str, limit: Optional[int] = None) -> list[ReferenceItem]:
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
        ref_ids = [rid for rid in ref_ids if _OA_ID_RE.match(rid)]
        if limit is not None:
            ref_ids = ref_ids[:limit]
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
        if not existing.venue_name and new.venue_name:
            existing.venue_name = new.venue_name
        if not existing.venue_issn and new.venue_issn:
            existing.venue_issn = new.venue_issn
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

def fetch_cited_by(doi: str, limit: Optional[int] = None) -> list[ReferenceItem]:
    doi_norm = normalize_doi(doi)
    if not doi_norm:
        raise ValueError('invalid doi')
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_ss = ex.submit(_ss_cited_by, doi_norm, limit)
        f_oa = ex.submit(_oa_cited_by, doi_norm, limit)
    ss_res: list[ReferenceItem] = []
    oa_res: list[ReferenceItem] = []
    try:
        ss_res = f_ss.result()
    except Exception as e:
        _log.warning('[fetch_cited_by] SS failed: %s', e)
    try:
        oa_res = f_oa.result()
    except Exception as e:
        _log.warning('[fetch_cited_by] OA failed: %s', e)
    return merge_dedup(ss_res, oa_res)


def fetch_references(doi: str, limit: Optional[int] = None) -> list[ReferenceItem]:
    doi_norm = normalize_doi(doi)
    if not doi_norm:
        raise ValueError('invalid doi')
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_ss = ex.submit(_ss_references, doi_norm, limit)
        f_oa = ex.submit(_oa_references, doi_norm, limit)
        f_cr = ex.submit(_cr_references, doi_norm, limit)
    ss_res: list[ReferenceItem] = []
    oa_res: list[ReferenceItem] = []
    cr_res: list[ReferenceItem] = []
    try:
        ss_res = f_ss.result()
    except Exception as e:
        _log.warning('[fetch_references] SS failed: %s', e)
    try:
        oa_res = f_oa.result()
    except Exception as e:
        _log.warning('[fetch_references] OA failed: %s', e)
    try:
        cr_res = f_cr.result()
    except Exception as e:
        _log.warning('[fetch_references] CR failed: %s', e)
    return merge_dedup(ss_res, oa_res, cr_res)
