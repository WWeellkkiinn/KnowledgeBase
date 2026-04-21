"""search_refs.py — Search paper metadata via OpenAlex → Semantic Scholar → arXiv.

Usage:
  python scripts/search_refs.py "<title>" [--year <year>] [--author "<author>"]
Output (stdout): JSON object with enriched metadata
"""
import argparse
import json
import sys
import urllib.parse

import httpx

TIMEOUT = 15


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("title")
    parser.add_argument("--year", default="")
    args = parser.parse_args()

    result = search(args.title, year=args.year)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def search(title: str, year: str = "") -> dict:
    base = {"title": title, "year": year, "authors": "", "doi": "", "pdf_url": "", "source": ""}

    # 1. OpenAlex
    r = _openalex(title, year)
    if r:
        return {**base, **r, "source": "openalex"}

    # 2. Semantic Scholar
    r = _semantic_scholar(title)
    if r:
        return {**base, **r, "source": "semantic_scholar"}

    # 3. arXiv
    r = _arxiv(title)
    if r:
        return {**base, **r, "source": "arxiv"}

    return {**base, "source": "not_found"}


def _openalex(title: str, year: str) -> dict | None:
    try:
        params = {"search": title, "select": "title,doi,open_access,publication_year,authorships"}
        if year:
            params["filter"] = f"publication_year:{year}"
        resp = httpx.get("https://api.openalex.org/works", params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None
        w = results[0]
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        pdf_url = w.get("open_access", {}).get("oa_url", "") or ""
        authors = ", ".join(
            a.get("author", {}).get("display_name", "") for a in w.get("authorships", [])[:3]
        )
        return {
            "title": w.get("title", title),
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
        doi = p.get("externalIds", {}).get("DOI", "")
        pdf_url = (p.get("openAccessPdf") or {}).get("url", "")
        authors = ", ".join(a.get("name", "") for a in p.get("authors", [])[:3])
        return {
            "title": p.get("title", title),
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
        return {
            "title": t.group(1).strip() if t else title,
            "doi": "",
            "pdf_url": f"https://arxiv.org/pdf/{aid}",
            "year": aid[:4] if aid[:4].isdigit() else "",
            "authors": "",
        }
    except Exception as e:
        print(f"[arxiv] {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    main()
