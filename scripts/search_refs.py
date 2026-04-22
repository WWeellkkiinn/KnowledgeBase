"""search_refs.py — Search paper metadata via OpenAlex → Semantic Scholar → arXiv.

Usage:
  python scripts/search_refs.py "<title>" [--year <year>] [--doi "<doi>"]
Output (stdout): JSON object with enriched metadata
"""
import argparse
import difflib
import json
import sys
import urllib.parse

import httpx

from config import CORE_API_KEY, UNPAYWALL_EMAIL as EMAIL

TIMEOUT = 15
TITLE_MATCH_THRESHOLD = 0.80


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("title")
    parser.add_argument("--year", default="")
    parser.add_argument("--doi", default="")
    args = parser.parse_args()

    result = search(args.title, year=args.year, doi=args.doi)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _normalize_title(t: str) -> str:
    t = t.lower().strip()
    # strip subtitle after ": " or " - "
    for sep in [": ", " - "]:
        if sep in t:
            t = t.split(sep)[0]
    # remove parenthetical acronyms like "(IT)" "(AI)"
    import re
    t = re.sub(r"\s*\([A-Z]{1,6}\)", "", t)
    return t.strip()


def _title_similar(a: str, b: str) -> bool:
    # check both raw and normalized versions
    ra = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
    if ra >= TITLE_MATCH_THRESHOLD:
        return True
    na, nb = _normalize_title(a), _normalize_title(b)
    return difflib.SequenceMatcher(None, na, nb).ratio() >= TITLE_MATCH_THRESHOLD


def _doi_complete(doi: str) -> bool:
    doi = doi.strip()
    return bool(doi) and not doi.endswith("/") and len(doi) > 8


def search(title: str, year: str = "", doi: str = "") -> dict:
    base = {"title": title, "year": year, "authors": "", "doi": doi, "pdf_url": "", "source": ""}

    # DOI-first path: validate returned title to catch mismatched DOIs in refs
    if _doi_complete(doi):
        r = _unpaywall(doi)
        if r and _title_similar(title, r.get("title", "")):
            return {**base, **r, "source": "unpaywall"}
        elif r:
            print(f"[unpaywall] doi title mismatch: {r.get('title')!r}", file=sys.stderr)

        r = _openalex_doi(doi)
        if r and _title_similar(title, r.get("title", "")):
            return {**base, **r, "source": "openalex_doi"}
        elif r:
            print(f"[openalex_doi] doi title mismatch: {r.get('title')!r}", file=sys.stderr)

        r = _ss_doi(doi)
        if r and _title_similar(title, r.get("title", "")):
            return {**base, **r, "source": "ss_doi"}
        elif r:
            print(f"[ss_doi] doi title mismatch: {r.get('title')!r}", file=sys.stderr)

    # Title-search fallback (with similarity validation)
    r = _openalex(title, year)
    if r:
        return {**base, **r, "source": "openalex"}

    r = _semantic_scholar(title)
    if r:
        return {**base, **r, "source": "semantic_scholar"}

    r = _arxiv(title)
    if r:
        return {**base, **r, "source": "arxiv"}

    r = _core(title, doi)
    if r:
        return {**base, **r, "source": "core"}

    return {**base, "source": "not_found"}


def _unpaywall(doi: str) -> dict | None:
    try:
        resp = httpx.get(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": EMAIL},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data.get("is_oa"):
            return None
        best = data.get("best_oa_location") or {}
        # url_for_pdf = direct PDF link; url = landing page (download_pdf.py handles both)
        pdf_url = best.get("url_for_pdf") or best.get("url") or ""
        if not pdf_url:
            return None
        return {
            "title": data.get("title", ""),
            "doi": doi,
            "pdf_url": pdf_url,
            "year": str(data.get("year", "")),
            "authors": "",
        }
    except Exception as e:
        print(f"[unpaywall] {e}", file=sys.stderr)
        return None


def _openalex_doi(doi: str) -> dict | None:
    try:
        resp = httpx.get(
            f"https://api.openalex.org/works/doi:{doi}",
            params={"mailto": EMAIL},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        w = resp.json()
        pdf_url = (w.get("best_oa_location") or {}).get("pdf_url") or \
                  w.get("open_access", {}).get("oa_url") or ""
        authors = ", ".join(
            a.get("author", {}).get("display_name", "") for a in w.get("authorships", [])[:3]
        )
        return {
            "title": w.get("title", ""),
            "doi": doi,
            "pdf_url": pdf_url or "",
            "year": str(w.get("publication_year", "")),
            "authors": authors,
        }
    except Exception as e:
        print(f"[openalex_doi] {e}", file=sys.stderr)
        return None


def _ss_doi(doi: str) -> dict | None:
    try:
        params = {"fields": "title,year,authors,openAccessPdf"}
        resp = httpx.get(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
            params=params,
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        p = resp.json()
        pdf_url = (p.get("openAccessPdf") or {}).get("url", "")
        authors = ", ".join(a.get("name", "") for a in p.get("authors", [])[:3])
        return {
            "title": p.get("title", ""),
            "doi": doi,
            "pdf_url": pdf_url,
            "year": str(p.get("year", "")),
            "authors": authors,
        }
    except Exception as e:
        print(f"[ss_doi] {e}", file=sys.stderr)
        return None


def _openalex(title: str, year: str) -> dict | None:
    try:
        params = {
            "search": title,
            "select": "title,doi,open_access,best_oa_location,publication_year,authorships",
            "mailto": EMAIL,
        }
        if year:
            params["filter"] = f"publication_year:{year}"
        resp = httpx.get("https://api.openalex.org/works", params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None
        w = results[0]
        returned_title = w.get("title", "")
        if not _title_similar(title, returned_title):
            print(f"[openalex] title mismatch: {returned_title!r}", file=sys.stderr)
            return None
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        pdf_url = (w.get("best_oa_location") or {}).get("pdf_url") or \
                  w.get("open_access", {}).get("oa_url", "") or ""
        authors = ", ".join(
            a.get("author", {}).get("display_name", "") for a in w.get("authorships", [])[:3]
        )
        return {
            "title": returned_title,
            "doi": doi,
            "pdf_url": pdf_url,
            "year": str(w.get("publication_year", "")),
            "authors": authors,
        }
    except Exception as e:
        print(f"[openalex] {e}", file=sys.stderr)
        return None


def _semantic_scholar(title: str) -> dict | None:
    try:
        params = {"query": title, "fields": "title,year,authors,externalIds,openAccessPdf", "limit": 1}
        resp = httpx.get("https://api.semanticscholar.org/graph/v1/paper/search", params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return None
        p = data[0]
        returned_title = p.get("title", "")
        if not _title_similar(title, returned_title):
            print(f"[semantic_scholar] title mismatch: {returned_title!r}", file=sys.stderr)
            return None
        doi = p.get("externalIds", {}).get("DOI", "")
        pdf_url = (p.get("openAccessPdf") or {}).get("url", "")
        authors = ", ".join(a.get("name", "") for a in p.get("authors", [])[:3])
        return {
            "title": returned_title,
            "doi": doi,
            "pdf_url": pdf_url,
            "year": str(p.get("year", "")),
            "authors": authors,
        }
    except Exception as e:
        print(f"[semantic_scholar] {e}", file=sys.stderr)
        return None


def _arxiv(title: str) -> dict | None:
    try:
        query = urllib.parse.quote(f'ti:"{title}"')
        resp = httpx.get(
            f"https://export.arxiv.org/api/query?search_query={query}&max_results=1",
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        import re
        entries = re.findall(r"<entry>(.*?)</entry>", resp.text, re.DOTALL)
        if not entries:
            return None
        entry = entries[0]
        arxiv_id = re.search(r"<id>.*?abs/([^<]+)</id>", entry)
        t = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
        if not arxiv_id:
            return None
        aid = arxiv_id.group(1).strip()
        returned_title = t.group(1).strip() if t else ""
        if returned_title and not _title_similar(title, returned_title):
            print(f"[arxiv] title mismatch: {returned_title!r}", file=sys.stderr)
            return None
        return {
            "title": returned_title or title,
            "doi": "",
            "pdf_url": f"https://arxiv.org/pdf/{aid}",
            "year": aid[:4] if aid[:4].isdigit() else "",
            "authors": "",
        }
    except Exception as e:
        print(f"[arxiv] {e}", file=sys.stderr)
        return None


def _core(title: str, doi: str = "") -> dict | None:
    import time
    time.sleep(2)  # CORE free tier: 5 req/10s
    try:
        query = f'doi:"{doi}"' if _doi_complete(doi) else f'title:"{title}"'
        params = {"q": query, "limit": 1, "apiKey": CORE_API_KEY}
        resp = httpx.get("https://api.core.ac.uk/v3/search/works", params=params, timeout=TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None
        w = results[0]
        returned_title = w.get("title", "")
        if not _title_similar(title, returned_title):
            print(f"[core] title mismatch: {returned_title!r}", file=sys.stderr)
            return None
        pdf_url = w.get("downloadUrl", "") or ""
        authors_raw = w.get("authors", [])
        authors = ", ".join(
            (a.get("name") or "") for a in authors_raw[:3] if a.get("name")
        )
        return {
            "title": returned_title,
            "doi": doi or w.get("doi", ""),
            "pdf_url": pdf_url,
            "year": str(w.get("yearPublished", "")),
            "authors": authors,
        }
    except Exception as e:
        print(f"[core] {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    main()
