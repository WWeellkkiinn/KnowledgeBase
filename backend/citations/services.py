"""BibTeX / APA citation generation.

Ported from services/citation_service.py — same algorithm, Django ORM.
No SQLAlchemy; operates on Django Paper model instances.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

import httpx

_log = logging.getLogger(__name__)

_OPENALEX_BASE = "https://api.openalex.org"
_TIMEOUT = 30

_BIBTEX_ESCAPE = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "@": r"{@}",
}
_CONTROL_CHARS = {chr(c) for c in range(32)} - {" "}


def bibtex_escape(s: str) -> str:
    if not s:
        return ""
    out = []
    for ch in s:
        if ch in _CONTROL_CHARS:
            out.append(" ")
        else:
            out.append(_BIBTEX_ESCAPE.get(ch, ch))
    return "".join(out)


def apa_sanitize(s: str) -> str:
    if not s:
        return ""
    return "".join(" " if ch in _CONTROL_CHARS else ch for ch in s)


def slug_for_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def parse_authors(authors_json) -> list[dict]:
    if not authors_json:
        return []

    def _split_name(full: str) -> dict:
        full = full.strip()
        if "," in full:
            family, _, given = full.partition(",")
            return {"family": family.strip(), "given": given.strip(), "full": full}
        parts = full.split()
        if len(parts) >= 2:
            return {"family": parts[-1], "given": " ".join(parts[:-1]), "full": full}
        return {"family": full, "given": "", "full": full}

    if isinstance(authors_json, str):
        s = authors_json.strip()
        if not s:
            return []
        for sep in [";", " and ", "&"]:
            if sep in s:
                return [_split_name(x) for x in s.split(sep) if x.strip()]
        return [_split_name(s)]

    out: list[dict] = []
    for a in authors_json:
        if isinstance(a, str):
            out.append(_split_name(a))
            continue
        if isinstance(a, dict):
            if "family" in a or "given" in a:
                full = (a.get("given", "") + " " + a.get("family", "")).strip() or \
                       a.get("display_name") or a.get("name", "")
                out.append({"family": a.get("family", ""), "given": a.get("given", ""), "full": full})
            else:
                name = a.get("display_name") or a.get("name") or ""
                out.append(_split_name(name))
    return out


_STOPWORDS = {"the", "a", "an", "of", "on", "in", "and", "for", "to", "from"}


def make_citation_key(authors: list[dict], year: Optional[int], title: str) -> str:
    if authors:
        author_part = slug_for_key(authors[0].get("family") or authors[0].get("full") or "anon")
    else:
        author_part = "anon"
    year_part = str(year) if year else "nd"
    title_tokens = re.findall(r"[A-Za-z0-9]+", title or "")
    title_part = ""
    for t in title_tokens:
        if t.lower() not in _STOPWORDS:
            title_part = slug_for_key(t)
            break
    return f"{author_part}{year_part}{title_part}" or "untitled"


def render_bibtex(
    *, key: str, entry_type: str, title: str, authors: list[dict],
    year: Optional[int], journal: Optional[str] = None,
    doi: Optional[str] = None, publisher: Optional[str] = None,
) -> str:
    fields = []
    if title:
        fields.append(("title", title))
    if authors:
        author_str = " and ".join(
            (a.get("family", "") + (", " + a.get("given", "") if a.get("given") else ""))
            for a in authors
        )
        fields.append(("author", author_str))
    if year is not None:
        fields.append(("year", str(year)))
    if journal:
        fields.append(("journal", journal))
    if publisher:
        fields.append(("publisher", publisher))
    if doi:
        fields.append(("doi", doi))

    lines = [f"@{entry_type}{{{key},"]
    for k, v in fields:
        lines.append(f"  {k} = {{{bibtex_escape(v)}}},")
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.append("}")
    return "\n".join(lines)


def render_apa(
    *, title: str, authors: list[dict], year: Optional[int],
    journal: Optional[str] = None, doi: Optional[str] = None,
) -> str:
    def _initials(given: str) -> str:
        if not given:
            return ""
        return " ".join(p[0].upper() + "." for p in given.split() if p)

    author_strs = []
    for a in authors:
        family = apa_sanitize(a.get("family", ""))
        initials = _initials(apa_sanitize(a.get("given", "")))
        if family and initials:
            author_strs.append(f"{family}, {initials}")
        elif family:
            author_strs.append(family)
        elif a.get("full"):
            author_strs.append(apa_sanitize(a["full"]))

    if len(author_strs) >= 2:
        author_part = ", ".join(author_strs[:-1]) + ", & " + author_strs[-1]
    elif author_strs:
        author_part = author_strs[0]
    else:
        author_part = ""

    parts = []
    if author_part:
        parts.append(author_part + ".")
    parts.append(f"({year if year else 'n.d.'}).")
    parts.append(f"{apa_sanitize(title)}." if title else "")
    if journal:
        parts.append(f"{apa_sanitize(journal)}.")
    if doi:
        parts.append(f"https://doi.org/{apa_sanitize(doi)}")
    return " ".join(p for p in parts if p).strip()


def _fetch_openalex(doi: str) -> Optional[dict]:
    import os
    mailto = os.environ.get("UNPAYWALL_EMAIL") or None
    params = {"mailto": mailto} if mailto else {}
    try:
        resp = httpx.get(f"{_OPENALEX_BASE}/works/doi:{doi}", params=params, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return None
        w = resp.json()
    except Exception as e:
        _log.warning("[citation] openalex %s failed: %s", doi, e)
        return None
    authors = [
        {"display_name": (a.get("author") or {}).get("display_name", "")}
        for a in (w.get("authorships") or [])
    ]
    return {
        "title": w.get("title", ""),
        "year": w.get("publication_year"),
        "authors": authors,
        "journal": ((w.get("primary_location") or {}).get("source") or {}).get("display_name"),
    }


def generate_citation(paper) -> dict:
    """Generate BibTeX + APA for a Paper Django model. Returns {bibtex, apa, citation_key}."""
    from journals.models import Journal

    title = paper.title or ""
    year = paper.year
    authors = parse_authors(paper.authors_json)
    doi = paper.doi or ""

    journal_name: Optional[str] = None
    publisher: Optional[str] = None
    if paper.journal_id:
        try:
            j = Journal.objects.get(pk=paper.journal_id)
            journal_name = j.name
            publisher = j.publisher
        except Journal.DoesNotExist:
            pass

    if (not title or not authors or not year) and doi:
        meta = _fetch_openalex(doi)
        if meta:
            title = title or meta.get("title", "")
            year = year or meta.get("year")
            if not authors:
                authors = parse_authors(meta.get("authors", []))
            journal_name = journal_name or meta.get("journal")

    key = make_citation_key(authors, year, title)
    bibtex = render_bibtex(
        key=key,
        entry_type="article" if journal_name else "misc",
        title=title, authors=authors, year=year,
        journal=journal_name, doi=doi or None, publisher=publisher,
    )
    apa = render_apa(title=title, authors=authors, year=year, journal=journal_name, doi=doi or None)
    return {"citation_key": key, "bibtex": bibtex, "apa": apa}
