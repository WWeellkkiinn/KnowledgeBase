#!/usr/bin/env python3
"""Download a PDF from a URL to a local file.

Usage:
    python scripts/download_pdf.py <url> <output_path>

Exit codes:
    0  success
    1  failure (reason printed to stderr)
"""

import re
import sys
import urllib.parse
from pathlib import Path

import httpx

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

# (host_fragment_or_None, regex_on_html) — first group = next URL (may be relative)
_LANDING_PAGE_RULES = [
    # Harvard DASH: bitstreams/<uuid>/download
    ("dash.harvard.edu", r'<a\s[^>]*href=["\']([^"\']*bitstreams/[^"\']+/download)["\']'),
    # Gary King's Harvard site: abstract .shtml → companion .pdf
    ("gking.harvard.edu", r'<a\s[^>]*href=["\']([^"\'\s]+\.pdf)["\']'),
    # RePEc IDEAS: "Downloads" uses a <form> with <input name="url" value="...">
    ("ideas.repec.org",
     r'<input [^>]*name=["\']url["\'][^>]*value=["\'](https?://[^"\']+)["\']'),
    # DSpace generic: /bitstream/ paths ending .pdf
    (None, r'<a\s[^>]*href=["\']([^"\']*bitstream[^"\']+\.pdf[^"\']*)["\']'),
]


def _extract_pdf_link(page_url: str, html: str) -> str | None:
    for host_frag, pattern in _LANDING_PAGE_RULES:
        if host_frag and host_frag not in page_url:
            continue
        m = re.search(pattern, html, re.I)
        if not m:
            continue
        return urllib.parse.urljoin(page_url, m.group(1))
    return None


def download(url: str, output_path: str) -> bool:
    if "ssrn.com" in url:
        return _download_via_browser(url, output_path)
    try:
        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
            return _fetch(client, url, output_path, referer=None, depth=0)
    except httpx.HTTPError as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return False


def _fetch(client: httpx.Client, url: str, output_path: str,
           referer: str | None, depth: int) -> bool:
    if depth > MAX_HOPS:
        print(f"too many landing-page hops (>{MAX_HOPS})", file=sys.stderr)
        return False

    extra = {"Referer": referer} if referer else {}
    try:
        resp = client.get(url, headers=extra)
    except httpx.TimeoutException:
        print("timeout", file=sys.stderr)
        return False

    if resp.status_code not in (200, 202):
        print(f"HTTP {resp.status_code}  ({url})", file=sys.stderr)
        return False

    content = resp.content
    ct = resp.headers.get("content-type", "")
    final_url = str(resp.url)

    if "pdf" in ct.lower() or content.startswith(b"%PDF"):
        with open(output_path, "wb") as f:
            f.write(content)
        print(f"ok  {len(content)//1024} KB  →  {output_path}")
        return True

    # Landing-page links appear within the first few KB; cap decode to bound memory.
    html_head = content[:262144].decode("utf-8", errors="ignore")
    pdf_link = _extract_pdf_link(final_url, html_head)
    if pdf_link and pdf_link != final_url:
        print(f"landing → {pdf_link}", file=sys.stderr)
        return _fetch(client, pdf_link, output_path, referer=final_url, depth=depth + 1)

    print(f"not a PDF (content-type: {ct!r})", file=sys.stderr)
    return False


def _download_via_browser(url: str, output_path: str) -> bool:
    """Stealth-browser download path for Cloudflare-protected hosts (SSRN)."""
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        print("patchright not installed (required for SSRN/Cloudflare sites)",
              file=sys.stderr)
        return False

    ctx = None
    try:
        user_data_dir = Path(__file__).resolve().parent.parent / ".cache" / "browser_profile"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                channel="chrome",
                headless=False,
                accept_downloads=True,
                no_viewport=True,
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            btn = page.locator('a:has-text("Download This Paper")').first
            btn.wait_for(timeout=90000, state="visible")
            # Dismiss OneTrust cookie banner if it intercepts the click
            try:
                page.locator("#onetrust-accept-btn-handler").click(timeout=3000)
            except Exception:
                pass
            with page.expect_download(timeout=60000) as dl_info:
                btn.click()
            dl_info.value.save_as(str(output_path))
            size_kb = Path(output_path).stat().st_size // 1024
            print(f"ok  {size_kb} KB  →  {output_path}")
            return True
    except Exception as e:
        print(f"browser fail: {type(e).__name__}: {e}", file=sys.stderr)
        return False
    finally:
        if ctx is not None:
            try:
                ctx.close()
            except Exception:
                pass


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: download_pdf.py <url> <output_path>", file=sys.stderr)
        sys.exit(1)
    ok = download(sys.argv[1], sys.argv[2])
    sys.exit(0 if ok else 1)
