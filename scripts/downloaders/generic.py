"""通用 PDF 下载器 — httpx + landing page 解析 + Unpaywall fallback。

处理所有 nber/ssrn 以外的 URL。
内部流程：
  1. httpx 直接下载（支持 landing page 跳转）
  2. 若重定向落到 ssrn.com，交给 ssrn handler
  3. 若下载失败且 URL 含 DOI，查询 Unpaywall 并重试
"""
import re
import urllib.parse

import httpx

from . import ssrn
from .unpaywall import extract_doi, lookup_pdf_url

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "application/pdf,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_HOPS = 3
# Wayback Machine 冷缓存响应慢，需要更长超时
_SLOW_DOMAINS = ("archive.org",)
_SLOW_TIMEOUT = httpx.Timeout(90.0, connect=30.0)

_LANDING_PAGE_RULES = [
    ("dash.harvard.edu", r'<a\s[^>]*href=["\']([^"\']*bitstreams/[^"\']+/download)["\']'),
    ("gking.harvard.edu", r'<a\s[^>]*href=["\']([^"\'\s]+\.pdf)["\']'),
    ("ideas.repec.org",
     r'<input [^>]*name=["\']url["\'][^>]*value=["\'](https?://[^"\']+)["\']'),
    (None, r'<a\s[^>]*href=["\']([^"\']*bitstream[^"\']+\.pdf[^"\']*)["\']'),
]


def can_handle(url: str) -> bool:
    return True


def download(url: str, output_path: str) -> tuple[bool, str]:
    timeout = _SLOW_TIMEOUT if any(d in url for d in _SLOW_DOMAINS) else 30
    try:
        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=timeout) as client:
            ok, msg, final_url = _fetch(client, url, output_path, referer=None, depth=0)
            if ok:
                return True, msg
            if "ssrn.com" in (final_url or ""):
                return ssrn.download(final_url, output_path)
            # Unpaywall fallback
            doi = extract_doi(url) or extract_doi(final_url or "")
            if doi:
                pdf_url = lookup_pdf_url(doi)
                if pdf_url and pdf_url != url:
                    ok2, msg2, _ = _fetch(client, pdf_url, output_path, referer=None, depth=0)
                    if ok2:
                        return True, msg2 + "  [via unpaywall]"
            return False, msg
    except httpx.HTTPError as e:
        return False, f"{type(e).__name__}: {e}"


def _fetch(
    client: httpx.Client,
    url: str,
    output_path: str,
    referer: str | None,
    depth: int,
) -> tuple[bool, str, str]:
    if depth > MAX_HOPS:
        return False, f"too many landing-page hops (>{MAX_HOPS})", url

    extra = {"Referer": referer} if referer else {}
    try:
        resp = client.get(url, headers=extra)
    except httpx.TimeoutException:
        return False, "timeout", url

    final_url = str(resp.url)

    if resp.status_code not in (200, 202):
        return False, f"HTTP {resp.status_code}  ({url})", final_url

    content = resp.content
    ct = resp.headers.get("content-type", "")

    if "pdf" in ct.lower() or content.startswith(b"%PDF"):
        try:
            with open(output_path, "wb") as f:
                f.write(content)
        except OSError as e:
            return False, f"write failed: {e}", final_url
        return True, f"ok  {len(content) // 1024} KB  →  {output_path}", final_url

    html_head = content[:262144].decode("utf-8", errors="ignore")
    pdf_link = _extract_pdf_link(final_url, html_head)
    if pdf_link and pdf_link != final_url:
        return _fetch(client, pdf_link, output_path, referer=final_url, depth=depth + 1)

    return False, f"not a PDF (content-type: {ct!r})", final_url


def _extract_pdf_link(page_url: str, html: str) -> str | None:
    for host_frag, pattern in _LANDING_PAGE_RULES:
        if host_frag and host_frag not in page_url:
            continue
        m = re.search(pattern, html, re.I)
        if not m:
            continue
        return urllib.parse.urljoin(page_url, m.group(1))
    return None
