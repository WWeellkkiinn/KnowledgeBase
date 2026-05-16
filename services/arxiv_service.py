"""arXiv 检索服务：按分类或关键词拉取最近论文。

公开 API:
    fetch_arxiv_recent(categories, hours, max_per_category)
    fetch_arxiv_by_keywords(keywords, hours, max_results)

实现要点：
    - 调 arXiv ATOM API (http://export.arxiv.org/api/query)
    - 硬性 3.5s/请求 限速（threading.Lock 串行同进程并发）
    - 失败返回 [] + warning 日志，不抛
    - published_at 解析后转为 UTC naive datetime（与项目其他模块一致）
"""
from __future__ import annotations

import atexit
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import quote

import httpx

_log = logging.getLogger(__name__)

_API = "http://export.arxiv.org/api/query"
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
_RATE_LIMIT_SEC = 3.5
_TIMEOUT = 30.0

# 进程内串行 + 限速时钟
_RATE_LOCK = threading.Lock()
_LAST_CALL_TS: float = 0.0

# 模块级 httpx.Client 复用：避免每次新建 SSL/TCP 池开销
_CLIENT = httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": "KnowledgeBase/1.0"})
atexit.register(_CLIENT.close)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _rate_limited_get(url: str) -> Optional[str]:
    """以 3.5s/请求 节流拉取 arXiv ATOM 响应文本。失败返回 None。

    锁只用来排队 + 占位下一次允许调用的时间戳；真正的 sleep + HTTP 在锁外，
    避免一个 30s 慢请求把所有并发线程全堵死。
    """
    global _LAST_CALL_TS
    with _RATE_LOCK:
        now = time.monotonic()
        wait = _RATE_LIMIT_SEC - (now - _LAST_CALL_TS)
        if wait < 0:
            wait = 0.0
        # 占位：让排队的下一个请求时间戳错开 3.5s，不靠真实完成时间
        _LAST_CALL_TS = max(_LAST_CALL_TS + _RATE_LIMIT_SEC, now + _RATE_LIMIT_SEC)
    if wait > 0:
        time.sleep(wait)
    try:
        resp = _CLIENT.get(url)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        _log.warning("arXiv API 调用失败 url=%s err=%s", url, exc)
        return None


_CAT_RE = re.compile(r"[A-Za-z][\w.\-]{0,32}")
_KW_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize_categories(categories: list[str]) -> list[str]:
    out: list[str] = []
    for c in categories:
        s = (c or "").strip()
        if s and _CAT_RE.fullmatch(s):
            out.append(s)
        elif s:
            _log.warning("arXiv: 丢弃无效 category %r", c)
    return out


def _sanitize_keywords(keywords: list[str]) -> list[str]:
    out: list[str] = []
    for k in keywords:
        if not isinstance(k, str):
            continue
        s = k.replace('"', '').replace('\\', '')
        s = _KW_CTRL_RE.sub("", s).strip()[:100]
        if s:
            out.append(s)
    return out


def _strip_version(arxiv_id_url: str) -> str:
    """从 http://arxiv.org/abs/2501.12345v2 抽裸 id 2501.12345。"""
    raw = arxiv_id_url.rsplit("/", 1)[-1]
    # 去掉 vN 后缀
    if "v" in raw:
        base, _, ver = raw.rpartition("v")
        if ver.isdigit():
            return base
    return raw


def _parse_published(text: str) -> Optional[datetime]:
    """解析 ISO 8601 / RFC2822 时间为 UTC naive datetime。"""
    if not text:
        return None
    try:
        # 优先 ISO 8601: 2026-05-15T10:00:00Z
        s = text.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _parse_feed(xml_text: str) -> list[dict]:
    """解析 ATOM feed -> list[dict]。"""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        _log.warning("arXiv ATOM 解析失败 err=%s", exc)
        return []

    out: list[dict] = []
    for entry in root.findall("atom:entry", _NS):
        id_el = entry.find("atom:id", _NS)
        if id_el is None or not (id_el.text or "").strip():
            continue
        arxiv_id = _strip_version(id_el.text.strip())

        title_el = entry.find("atom:title", _NS)
        title = (title_el.text or "").strip() if title_el is not None else ""

        abs_el = entry.find("atom:summary", _NS)
        abstract = (abs_el.text or "").strip() if abs_el is not None else ""

        authors = [
            (n.text or "").strip()
            for n in entry.findall("atom:author/atom:name", _NS)
            if (n.text or "").strip()
        ]

        published_at = _parse_published(
            (entry.findtext("atom:published", default="", namespaces=_NS) or "")
        )
        updated_at = _parse_published(
            (entry.findtext("atom:updated", default="", namespaces=_NS) or "")
        )

        primary_el = entry.find("arxiv:primary_category", _NS)
        primary_category = (
            primary_el.attrib.get("term", "") if primary_el is not None else ""
        )

        categories = [
            c.attrib.get("term", "")
            for c in entry.findall("atom:category", _NS)
            if c.attrib.get("term")
        ]

        out.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "primary_category": primary_category,
                "categories": categories,
                "published_at": published_at,
                "updated_at": updated_at,
                "pdf_url": f"http://arxiv.org/pdf/{arxiv_id}.pdf",
                "abs_url": f"http://arxiv.org/abs/{arxiv_id}",
            }
        )
    return out


def _filter_recent(items: list[dict], hours: int) -> list[dict]:
    """按 published_at 过滤最近 hours 小时（含）。

    hours<=0 显式返回空列表（语义：不取最近任何窗口），不同于 hours=None。
    """
    if hours <= 0:
        return []
    now = _utcnow_naive()
    cutoff_sec = hours * 3600
    kept: list[dict] = []
    for it in items:
        pub = it.get("published_at")
        if not isinstance(pub, datetime):
            continue
        if (now - pub).total_seconds() <= cutoff_sec:
            kept.append(it)
    return kept


def fetch_arxiv_recent(
    categories: list[str],
    hours: int = 24,
    max_per_category: int = 50,
) -> list[dict]:
    """按 arXiv 分类拉取最近 hours 小时新提交论文。

    Args:
        categories: arXiv 分类列表，如 ['cs.AI', 'cs.CL']
        hours: 时间窗口（小时），按 published_at 过滤
        max_per_category: 单次请求 max_results（API 入参，总量上限）

    Returns:
        list[dict]，字段：arxiv_id, title, abstract, authors,
        primary_category, categories, published_at, updated_at,
        pdf_url, abs_url
    """
    if not categories:
        return []
    valid_categories = _sanitize_categories(categories)
    if not valid_categories:
        return []
    # 手工拼 URL：用 +OR+ 作分隔符（arXiv 要求字面 "+OR+"，URL 编码后会变 %2BOR%2B 失效），
    # 单 category 仍用 quote(safe='') 转义防注入
    query = "+OR+".join(f"cat:{quote(c, safe='')}" for c in valid_categories)
    url = (
        f"{_API}?search_query={query}"
        f"&sortBy=submittedDate&sortOrder=descending&start=0"
        f"&max_results={int(max_per_category)}"
    )
    xml_text = _rate_limited_get(url)
    if not xml_text:
        return []
    items = _parse_feed(xml_text)
    return _filter_recent(items, hours)


def fetch_arxiv_by_keywords(
    keywords: list[str],
    hours: int = 24,
    max_results: int = 50,
) -> list[dict]:
    """按关键词 AND 检索最近 hours 小时论文。"""
    if not keywords:
        return []
    sanitized_kws = _sanitize_keywords(keywords)
    if not sanitized_kws:
        return []
    # 关键词外面包裹双引号一并 quote（双引号本身要 %22），AND 同样用字面 +AND+
    parts = [f'all:{quote(chr(34) + k + chr(34), safe="")}' for k in sanitized_kws]
    query = "+AND+".join(parts)
    url = (
        f"{_API}?search_query={query}"
        f"&sortBy=submittedDate&sortOrder=descending&start=0"
        f"&max_results={int(max_results)}"
    )
    xml_text = _rate_limited_get(url)
    if not xml_text:
        return []
    items = _parse_feed(xml_text)
    return _filter_recent(items, hours)
