"""search_refs.py — Search paper metadata via OpenAlex → Semantic Scholar → arXiv.

Usage:
  python scripts/search_refs.py "<title>" [--year <year>] [--doi "<doi>"]
Output (stdout): JSON object with enriched metadata
"""
import argparse
import difflib
import json
import sys
import time
import urllib.parse

import httpx

from config import CORE_API_KEY, SS_API_KEY, UNPAYWALL_EMAIL as EMAIL

# 有 API key 时限速 1 req/s；匿名时限流严格，做指数退避
_SS_HEADERS = {"x-api-key": SS_API_KEY} if SS_API_KEY else {}
_SS_INTERVAL = 1.0  # seconds between SS requests
_ss_last_call = 0.0
SS_RETRY_WAITS = (5,)  # 有 key 后只需重试一次


def _ss_get(url: str, params: dict) -> httpx.Response | None:
    """Semantic Scholar GET with rate limiting and 429 backoff."""
    global _ss_last_call
    elapsed = time.time() - _ss_last_call
    if elapsed < _SS_INTERVAL:
        time.sleep(_SS_INTERVAL - elapsed)
    for i, wait in enumerate((0, *SS_RETRY_WAITS)):
        if wait:
            time.sleep(wait)
        _ss_last_call = time.time()
        resp = httpx.get(url, params=params, headers=_SS_HEADERS, timeout=TIMEOUT)
        if resp.status_code != 429:
            return resp
        print(f"[ss] 429 rate-limited, retry {i + 1}/{len(SS_RETRY_WAITS)} after {wait}s",
              file=sys.stderr)
    return None

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
    import re
    t = t.strip()
    # 先清理括号缩写（大写时才能匹配），再转小写
    t = re.sub(r"\s*\([A-Z]{1,6}\)", "", t)
    t = t.lower()
    # strip subtitle after ": " or " - "
    for sep in [": ", " - "]:
        if sep in t:
            t = t.split(sep)[0]
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
    best: dict = {}  # 记录最佳元数据命中（可能无 pdf_url）

    def _accept(r: dict | None, source: str) -> bool:
        """命中且标题匹配则更新 best，有 pdf_url 时立即返回 True。"""
        nonlocal best
        if not r:
            return False
        if not _title_similar(title, r.get("title", r.get("title", title))):
            return False
        merged = {**base, **r, "source": source}
        if not best or (not best.get("pdf_url") and r.get("pdf_url")):
            best = merged
        return bool(r.get("pdf_url"))

    # DOI-first path
    if _doi_complete(doi):
        r = _unpaywall(doi)
        if r and _title_similar(title, r.get("title", "")):
            if _accept(r, "unpaywall"):
                return best
        elif r:
            print(f"[unpaywall] doi title mismatch: {r.get('title')!r}", file=sys.stderr)

        r = _openalex_doi(doi)
        if r and _title_similar(title, r.get("title", "")):
            if _accept(r, "openalex_doi"):
                return best
        elif r:
            print(f"[openalex_doi] doi title mismatch: {r.get('title')!r}", file=sys.stderr)

        r = _ss_doi(doi)
        if r and _title_similar(title, r.get("title", "")):
            if _accept(r, "ss_doi"):
                return best
        elif r:
            print(f"[ss_doi] doi title mismatch: {r.get('title')!r}", file=sys.stderr)

    # Title-search fallback — 逐源尝试，有 pdf_url 即返回，否则记录元数据继续
    for fn, src in [
        (lambda: _openalex(title, year), "openalex"),
        (lambda: _semantic_scholar(title), "semantic_scholar"),
        (lambda: _arxiv(title), "arxiv"),
        (lambda: _repec(title, doi), "repec"),
        (lambda: _core(title, doi), "core"),
        (lambda: _zenodo(title, year), "zenodo"),
        (lambda: _pubmed(title, year), "pubmed"),
        (lambda: _scholarly(title), "scholarly"),
    ]:
        r = fn()
        if _accept(r, src):
            return best

    return best if best else {**base, "source": "not_found"}


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
        resp = _ss_get(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
            {"fields": "title,year,authors,openAccessPdf"},
        )
        if resp is None or resp.status_code != 200:
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
        resp = _ss_get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            {"query": title, "fields": "title,year,authors,externalIds,openAccessPdf", "limit": 1},
        )
        if resp is None:
            return None
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


def _repec(title: str, doi: str = "") -> dict | None:
    """搜索 IDEAS.RePEC（经济学/金融/管理学论文）。"""
    import re as _re
    try:
        query = urllib.parse.quote(title)
        resp = httpx.get(
            f"https://ideas.repec.org/cgi-bin/htsearch?q={query}&cmd=Search",
            timeout=TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"},
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return None

        # 找首条结果链接（形如 /a/xxx.html 或 /p/xxx.html）
        m = _re.search(
            r'href="(https://ideas\.repec\.org/(?:a|p|b)/[^"]+\.html)"',
            resp.text,
        )
        if not m:
            return None
        paper_url = m.group(1)

        paper_resp = httpx.get(
            paper_url, timeout=TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"},
            follow_redirects=True,
        )
        if paper_resp.status_code != 200:
            return None

        # 提取标题
        t = _re.search(r"<h1[^>]*>(.*?)</h1>", paper_resp.text, _re.DOTALL)
        returned_title = _re.sub(r"<[^>]+>", "", t.group(1)).strip() if t else ""
        if returned_title and not _title_similar(title, returned_title):
            print(f"[repec] title mismatch: {returned_title!r}", file=sys.stderr)
            return None

        # 找 PDF 直链或下载链接
        pdf_url = ""
        pdf_m = _re.search(r'href="([^"]+\.pdf[^"]*)"', paper_resp.text, _re.I)
        if pdf_m:
            pdf_url = urllib.parse.urljoin(paper_url, pdf_m.group(1))
        else:
            dl_m = _re.search(
                r'href="(https?://[^"]+)"[^>]*>\s*(?:Download full text|Full text|Download)',
                paper_resp.text, _re.I,
            )
            if dl_m:
                pdf_url = dl_m.group(1)

        if not pdf_url:
            return None

        return {
            "title": returned_title or title,
            "doi": doi,
            "pdf_url": pdf_url,
            "year": "",
            "authors": "",
        }
    except Exception as e:
        print(f"[repec] {e}", file=sys.stderr)
        return None


def _zenodo(title: str, year: str = "") -> dict | None:
    """Zenodo 开放获取仓库搜索（M4.1）。"""
    try:
        q = f'title:"{title}"'
        if year:
            q += f" AND publication_date:[{year}-01-01 TO {year}-12-31]"
        resp = httpx.get(
            "https://zenodo.org/api/records",
            params={"q": q, "type": "publication", "size": 3},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        hits = resp.json().get("hits", {}).get("hits", [])
        if not hits:
            return None
        rec = hits[0]
        meta = rec.get("metadata", {})
        returned_title = meta.get("title", "")
        if not _title_similar(title, returned_title):
            print(f"[zenodo] title mismatch: {returned_title!r}", file=sys.stderr)
            return None
        doi = meta.get("doi", "")
        pdf_url = ""
        for f in rec.get("files", []):
            key = f.get("key", "")
            if f.get("type") == "pdf" or key.lower().endswith(".pdf"):
                pdf_url = f.get("links", {}).get("self", "")
                break
        authors = ", ".join(c.get("name", "") for c in meta.get("creators", [])[:3])
        return {
            "title": returned_title,
            "doi": doi,
            "pdf_url": pdf_url,
            "year": str(meta.get("publication_date", year))[:4],
            "authors": authors,
        }
    except Exception as e:
        print(f"[zenodo] {e}", file=sys.stderr)
        return None


def _pubmed(title: str, year: str = "") -> dict | None:
    """PubMed/PMC 搜索，有开放获取 PDF 时直接返回（M4.2）。"""
    try:
        term = f'"{title}"[Title]'
        if year:
            term += f" AND {year}[PDAT]"
        resp = httpx.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={"db": "pubmed", "term": term, "retmax": 3, "retmode": "json"},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        ids = resp.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return None
        pmid = ids[0]

        sum_resp = httpx.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params={"db": "pubmed", "id": pmid, "retmode": "json"},
            timeout=TIMEOUT,
        )
        if sum_resp.status_code != 200:
            return None
        result = sum_resp.json().get("result", {}).get(pmid, {})
        returned_title = result.get("title", "")
        if returned_title and not _title_similar(title, returned_title):
            print(f"[pubmed] title mismatch: {returned_title!r}", file=sys.stderr)
            return None

        doi = ""
        for uid in result.get("articleids", []):
            if uid.get("idtype") == "doi":
                doi = uid.get("value", "")
                break
        authors_list = [a.get("name", "") for a in result.get("authors", [])[:3]]
        year_pub = result.get("pubdate", "")[:4]

        # 尝试找 PMC 开放获取 PDF
        pdf_url = ""
        link_resp = httpx.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi",
            params={"dbfrom": "pubmed", "db": "pmc", "id": pmid, "retmode": "json"},
            timeout=TIMEOUT,
        )
        if link_resp.status_code == 200:
            for ls in link_resp.json().get("linksets", []):
                for ld in ls.get("linksetdbs", []):
                    if ld.get("dbto") == "pmc":
                        pmc_ids = ld.get("links", [])
                        if pmc_ids:
                            pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_ids[0]}/pdf/"

        return {
            "title": returned_title or title,
            "doi": doi,
            "pdf_url": pdf_url,
            "year": year_pub or year,
            "authors": ", ".join(authors_list),
        }
    except Exception as e:
        print(f"[pubmed] {e}", file=sys.stderr)
        return None


def _scholarly(title: str) -> dict | None:
    """Google Scholar 搜索（最后 fallback，有限速风险）。"""
    import threading

    result: list = [None]
    exc: list = [None]

    def _fetch():
        try:
            from scholarly import scholarly as _sc
            results = _sc.search_pubs(title)
            result[0] = next(results, None)
        except Exception as e:
            exc[0] = e

    t = threading.Thread(target=_fetch, daemon=True)
    t.start()
    t.join(timeout=30)
    if t.is_alive():
        print("[scholarly] timeout (30s)", file=sys.stderr)
        return None
    if exc[0]:
        print(f"[scholarly] {exc[0]}", file=sys.stderr)
        return None
    pub = result[0]

    if not pub:
        return None
    returned_title = pub.get("bib", {}).get("title", "")
    if returned_title and not _title_similar(title, returned_title):
        print(f"[scholarly] title mismatch: {returned_title!r}", file=sys.stderr)
        return None
    pdf_url = pub.get("eprint_url", "") or ""
    year = str(pub.get("bib", {}).get("pub_year", ""))
    return {
        "title": returned_title or title,
        "doi": "",
        "pdf_url": pdf_url,
        "year": year,
        "authors": "",
    }


if __name__ == "__main__":
    main()
