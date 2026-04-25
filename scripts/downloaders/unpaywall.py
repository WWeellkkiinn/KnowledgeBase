"""Unpaywall helper — 给定 DOI 返回 OA PDF 直链（无则返回 None）。

不是 handler，供 generic.py 调用。
"""
import re

import httpx

_EMAIL = "<UNPAYWALL_EMAIL>"
# 匹配 DOI，不吃 ? # & 以及尾部标点
_DOI_RE = re.compile(r"10\.\d{4,}/[^\s?#&\"'<>]+")
_DOI_TRAIL = re.compile(r"[.,;:)\]]+$")


def extract_doi(url: str) -> str | None:
    m = re.match(r"https?://(?:dx\.)?doi\.org/(10\.[^\s?#&\"'<>]+)", url)
    if m:
        return _DOI_TRAIL.sub("", m.group(1))
    m = _DOI_RE.search(url)
    return _DOI_TRAIL.sub("", m.group(0)) if m else None


def lookup_pdf_url(doi: str) -> str | None:
    """查询 Unpaywall，返回 OA PDF 直链；未找到或出错返回 None。"""
    try:
        r = httpx.get(
            f"https://api.unpaywall.org/v2/{doi}?email={_EMAIL}",
            timeout=15,
            follow_redirects=True,
        )
        data = r.json()
    except Exception:
        return None

    loc = data.get("best_oa_location") or {}
    return loc.get("url_for_pdf") or None
