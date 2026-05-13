"""NBER working paper downloader.

旧 URL 格式：http://www.nber.org/papers/w1234.pdf
新 URL 格式：https://www.nber.org/system/files/working_papers/w1234/w1234.pdf
"""
import re
from pathlib import Path

import httpx

_OLD_URL = re.compile(r"https?://(?:www\.)?nber\.org/papers/(w\d+)\.pdf", re.I)
_WID_RE = re.compile(r"working_papers/([wt]\d+)/")
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
    "Referer": "https://www.nber.org/",
}


def can_handle(url: str) -> bool:
    return "nber.org" in url


def download(url: str, output_path: str) -> tuple[bool, str]:
    m = _OLD_URL.match(url)
    if m:
        wid = m.group(1)
        url = f"https://www.nber.org/system/files/working_papers/{wid}/{wid}.pdf"

    try:
        with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=30) as client:
            resp = client.get(url)
    except httpx.HTTPError as e:
        return False, f"{type(e).__name__}: {e}"

    if resp.status_code == 403:
        # NBER soft-paywalls some papers; try Unpaywall with the constructed DOI
        from .unpaywall import extract_doi, lookup_pdf_url
        from . import generic
        doi = extract_doi(url)
        if not doi:
            wm = _WID_RE.search(url)
            if wm:
                doi = f"10.3386/{wm.group(1)}"
        if doi:
            alt = lookup_pdf_url(doi)
            if alt and alt != url:
                return generic.download(alt, output_path)
        return False, f"HTTP {resp.status_code}  ({url})"

    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}  ({url})"

    content = resp.content
    if "pdf" in resp.headers.get("content-type", "").lower() or content.startswith(b"%PDF"):
        try:
            Path(output_path).write_bytes(content)
        except OSError as e:
            return False, f"write failed: {e}"
        return True, f"ok  {len(content) // 1024} KB  →  {output_path}"

    return False, f"not a PDF (content-type: {resp.headers.get('content-type', '')!r})"
