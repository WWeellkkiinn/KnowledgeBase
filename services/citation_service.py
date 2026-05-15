"""CitationService —— 引文规范化 + BibTeX/APA 导出（M2.5）。

输入：paper 的 doi + metadata（OpenAlex 兜底）
输出：bibtex 字符串 + apa 字符串 + 落库到 `citations` 表（refreshed_at）

设计：
- 没有引入额外的 bibtex 第三方库；用纯字符串模板生成（M2.5 范围内够用）
- citation_key 规则：firstauthorlast + year + first significant word（小写、去标点）
- 转义：BibTeX 中的 `{}`, `\\`, `&`, `%`, `_`, `$`, `#` 字符必须保护
- APA 用 7th 风格简化版（不处理复杂情况如 et al 阈值差异）

幂等：再次生成更新 refreshed_at，bibtex/apa 文本覆盖；前端通过 refreshed_at 判断是否过期。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import models

from ._paths import ensure_scripts_on_path

_log = logging.getLogger(__name__)

_OPENALEX_BASE = "https://api.openalex.org"
_TIMEOUT = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ─── 字符串工具 ─────────────────────────────────────────────────────


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
    # `@` 不属于 BibTeX 字段值的合法字符 —— 若用户控制的 title/author 含
    # `@article{...}` 形态会被 .bib parser 视为新 entry 起点（注入风险）。
    # `@` 在花括号内严格说是合法字符，但安全起见替换为 HTML/普通转义。
    "@": r"{@}",
}

# 控制字符（包括 \r \n \t \x00-\x1f）一律剥成空格，避免跨字段污染 .bib
_CONTROL_CHARS = {chr(c) for c in range(32)} - {" "}


def bibtex_escape(s: str) -> str:
    """转义 BibTeX 特殊字符 + 清洗控制字符。`\\` 排在第一位避免二次转义。"""
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
    """APA 输出字段：去控制字符（含 \\r \\n \\t），保留可打印 ASCII + Unicode。"""
    if not s:
        return ""
    return "".join(" " if ch in _CONTROL_CHARS else ch for ch in s)


def slug_for_key(name: str) -> str:
    """citation key 用的 slug：纯字母数字、小写。"""
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


# ─── 作者解析 ───────────────────────────────────────────────────────


def parse_authors(authors_json) -> list[dict]:
    """authors_json 可能是 list[dict] / list[str] / str / None。规整成
    `[{"family": "...", "given": "...", "full": "..."}]`。
    """
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
        # 多作者分隔：分号 > " and " > "&"；纯逗号是有歧义的（既可能是作者间分隔，
        # 也可能是 "Family, Given" 格式），保守地不按逗号切。
        s = authors_json.strip()
        if not s:
            return []
        for sep in [";", " and ", "&"]:
            if sep in s:
                return [_split_name(x) for x in s.split(sep) if x.strip()]
        # 无可信分隔符 → 当作单作者（即使含逗号，_split_name 内会按 "Family, Given" 解析）
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
                out.append({"family": a.get("family", ""),
                            "given": a.get("given", ""),
                            "full": full})
            else:
                name = a.get("display_name") or a.get("name") or ""
                out.append(_split_name(name))
    return out


# ─── citation_key ──────────────────────────────────────────────────


_STOPWORDS = {"the", "a", "an", "of", "on", "in", "and", "for", "to", "from"}


def make_citation_key(authors: list[dict], year: Optional[int], title: str) -> str:
    """`{firstauthor}{year}{firstmeaningfultitleword}` (lowercase, ascii)."""
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


# ─── BibTeX / APA 生成 ────────────────────────────────────────────


def render_bibtex(
    *,
    key: str,
    entry_type: str,
    title: str,
    authors: list[dict],
    year: Optional[int],
    journal: Optional[str] = None,
    doi: Optional[str] = None,
    publisher: Optional[str] = None,
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
    # 去掉最后一行的逗号
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.append("}")
    return "\n".join(lines)


def render_apa(
    *,
    title: str,
    authors: list[dict],
    year: Optional[int],
    journal: Optional[str] = None,
    doi: Optional[str] = None,
) -> str:
    """APA 7th 简化版：Author, A. A., & Author, B. B. (Year). Title. Journal. https://doi.org/..."""
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

    safe_title = apa_sanitize(title)
    safe_journal = apa_sanitize(journal) if journal else None
    safe_doi = apa_sanitize(doi) if doi else None

    parts = []
    if author_part:
        parts.append(author_part + ".")
    parts.append(f"({year if year else 'n.d.'}).")
    parts.append(f"{safe_title}." if safe_title else "")
    if safe_journal:
        parts.append(f"{safe_journal}.")
    if safe_doi:
        parts.append(f"https://doi.org/{safe_doi}")
    return " ".join(p for p in parts if p).strip()


# ─── Service ───────────────────────────────────────────────────────


class CitationService:
    """生成 / 查询 / 落库 BibTeX & APA。"""

    def __init__(self, db_session: Optional[Session] = None) -> None:
        self.db_session = db_session

    def generate(self, session: Session, paper: models.Paper,
                 *, refresh: bool = False) -> models.Citation:
        """生成（或刷新）一条 citations 记录并返回。"""
        existing = session.execute(
            select(models.Citation).where(models.Citation.paper_id == paper.id)
        ).scalar_one_or_none()
        if existing is not None and not refresh:
            return existing

        # 字段优先取 paper 本地；缺失再 OpenAlex 兜底
        title = paper.title or ""
        year = paper.year
        authors = parse_authors(paper.authors_json)
        journal_name = paper.journal.name if paper.journal else None
        publisher = paper.journal.publisher if paper.journal else None
        doi = paper.doi or ""

        if (not title or not authors or not year) and doi:
            meta = self._fetch_openalex(doi)
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
        apa = render_apa(title=title, authors=authors, year=year,
                         journal=journal_name, doi=doi or None)

        if existing is None:
            citation = models.Citation(
                paper_id=paper.id,
                citation_key=key,
                bibtex=bibtex,
                apa=apa,
                refreshed_at=_utcnow(),
            )
            session.add(citation)
        else:
            existing.citation_key = key
            existing.bibtex = bibtex
            existing.apa = apa
            existing.refreshed_at = _utcnow()
            citation = existing
        session.flush()
        return citation

    def bibtex_for_all(self, session: Session) -> str:
        """全库 BibTeX 拼接（按 paper.id 顺序）。只取 bibtex 列，避免 ORM 全量 hydrate。"""
        rows = session.execute(
            select(models.Citation.bibtex).order_by(models.Citation.paper_id.asc())
        ).all()
        return "\n\n".join(b for (b,) in rows if b)

    # ─── OpenAlex 兜底 ─────────────────────────────────────────────

    def _openalex_mailto(self) -> Optional[str]:
        ensure_scripts_on_path()
        try:
            from config import UNPAYWALL_EMAIL  # type: ignore
            return UNPAYWALL_EMAIL or None
        except Exception:
            return None

    def _fetch_openalex(self, doi: str) -> Optional[dict]:
        from .reference_fetcher import normalize_doi as _normalize_doi
        doi = _normalize_doi(doi or "")
        if not doi:
            return None
        try:
            mailto = self._openalex_mailto()
            params = {"mailto": mailto} if mailto else {}
            resp = httpx.get(
                f"{_OPENALEX_BASE}/works/doi:{doi}", params=params, timeout=_TIMEOUT
            )
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
