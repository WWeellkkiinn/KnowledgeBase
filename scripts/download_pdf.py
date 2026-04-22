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
import httpx

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*",
}

# Patterns: (url_substring, regex_on_html) → extract first group as PDF URL
# Each entry: (host_fragment, href_pattern, url_prefix_if_relative)
_LANDING_PAGE_RULES = [
    # Harvard DASH: dash.harvard.edu/bitstreams/<uuid>/download
    ("dash.harvard.edu", r'href=["\']([^"\']*bitstreams/[^"\']+/download)["\']', "https://dash.harvard.edu"),
    # DSpace-based repos: /bitstream/ paths with .pdf
    (None, r'href=["\']([^"\']*bitstream[^"\']+\.pdf[^"\']*)["\']', None),
]


def _extract_pdf_link(page_url: str, html: str) -> str | None:
    for host_frag, pattern, prefix in _LANDING_PAGE_RULES:
        if host_frag and host_frag not in page_url:
            continue
        m = re.search(pattern, html, re.I)
        if not m:
            continue
        href = m.group(1)
        return urllib.parse.urljoin(page_url, href)
    return None


def download(url: str, output_path: str) -> bool:
    try:
        with httpx.Client(
            headers=HEADERS,
            follow_redirects=True,
            timeout=30,
        ) as client:
            resp = client.get(url)

        if resp.status_code not in (200, 202):
            print(f"HTTP {resp.status_code}", file=sys.stderr)
            return False

        content = resp.content
        ct = resp.headers.get("content-type", "")
        final_url = str(resp.url)

        if "pdf" not in ct.lower() and not content.startswith(b"%PDF"):
            # Try to extract a PDF link from the landing page HTML
            pdf_link = _extract_pdf_link(final_url, content.decode("utf-8", errors="ignore"))
            if pdf_link:
                print(f"landing page → {pdf_link}", file=sys.stderr)
                return download(pdf_link, output_path)
            print(f"not a PDF (content-type: {ct!r})", file=sys.stderr)
            return False

        with open(output_path, "wb") as f:
            f.write(content)

        print(f"ok  {len(content)//1024} KB  →  {output_path}")
        return True

    except httpx.TimeoutException:
        print("timeout", file=sys.stderr)
        return False
    except Exception as e:
        print(str(e), file=sys.stderr)
        return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: download_pdf.py <url> <output_path>", file=sys.stderr)
        sys.exit(1)

    ok = download(sys.argv[1], sys.argv[2])
    sys.exit(0 if ok else 1)
