"""M2.5 验收：CitationService BibTeX/APA 生成、转义、citation_key。"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from database import Base, enable_sqlite_foreign_keys, models
from services.citation_service import (
    CitationService,
    bibtex_escape,
    make_citation_key,
    parse_authors,
    render_apa,
    render_bibtex,
    slug_for_key,
)


@pytest.fixture()
def session(tmp_path: Path):
    db_file = tmp_path / "kb_cite.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


# ─── 转义 ────────────────────────────────────────────────────────────


def test_bibtex_escape_handles_special_chars():
    assert bibtex_escape("R&D") == r"R\&D"
    assert bibtex_escape("100% pure") == r"100\% pure"
    assert bibtex_escape("a_b") == r"a\_b"
    assert bibtex_escape("{nested}") == r"\{nested\}"


def test_bibtex_escape_protects_at_sign_injection():
    """攻击者控制 paper.title 含 `@article{evil` 不应被 .bib parser 解释为新 entry。"""
    out = bibtex_escape("normal @article{evil,")
    assert "@article" not in out  # @ 已被 {@} 包裹
    assert "{@}article" in out


def test_bibtex_escape_strips_control_chars():
    """\\r \\n \\t \\x00 等控制字符替换为空格，避免 .bib 字段跨行污染。"""
    out = bibtex_escape("a\r\nb\tc\x00d")
    assert "\r" not in out and "\n" not in out
    assert "\x00" not in out
    assert "a" in out and "b" in out and "c" in out and "d" in out


def test_bibtex_escape_textbackslash_no_double():
    """`\\` 转义结果应是 `\\textbackslash{}` 而非 `\\\\textbackslash{}`。"""
    out = bibtex_escape("a\\b")
    assert out == r"a\textbackslash{}b"


def test_bibtex_escape_empty():
    assert bibtex_escape("") == ""
    assert bibtex_escape(None) == ""


# ─── 作者解析 ───────────────────────────────────────────────────────


def test_parse_authors_dict_with_family():
    out = parse_authors([{"family": "Smith", "given": "John"}])
    assert out == [{"family": "Smith", "given": "John", "full": "John Smith"}]


def test_parse_authors_dict_display_name():
    out = parse_authors([{"display_name": "Jane Q. Doe"}])
    assert out[0]["family"] == "Doe"
    assert out[0]["given"] == "Jane Q."


def test_parse_authors_comma_string():
    out = parse_authors("Smith, John; Doe, Jane")
    assert len(out) == 2
    assert out[0]["family"] == "Smith"
    assert out[1]["family"] == "Doe"


def test_parse_authors_single_family_given_no_split():
    """单作者 "Smith, John" 不应被错误地拆为两个作者（修复 C1 审查发现）。"""
    out = parse_authors("Smith, John")
    assert len(out) == 1
    assert out[0]["family"] == "Smith"
    assert out[0]["given"] == "John"


def test_parse_authors_and_separator():
    """带 ' and ' 分隔的多作者字符串应正确拆分。"""
    out = parse_authors("Smith, J and Doe, J")
    assert len(out) == 2


def test_parse_authors_none_or_empty():
    assert parse_authors(None) == []
    assert parse_authors("") == []
    assert parse_authors([]) == []


# ─── citation_key ──────────────────────────────────────────────────


def test_make_citation_key_basic():
    key = make_citation_key(
        [{"family": "Smith", "given": "J"}],
        2020,
        "The Analysis of Innovation",
    )
    assert key == "smith2020analysis"  # "the" 是 stopword


def test_make_citation_key_no_authors_no_year():
    assert make_citation_key([], None, "X") == "anonndx"


def test_make_citation_key_with_punct_title():
    key = make_citation_key(
        [{"family": "O'Brien"}], 2021, "On Methods: A Survey."
    )
    # 注意：O'Brien -> "obrien" (apostrophe removed)
    assert key == "obrien2021methods"


# ─── render ─────────────────────────────────────────────────────────


def test_render_bibtex_article():
    out = render_bibtex(
        key="smith2020x",
        entry_type="article",
        title="A Study",
        authors=[{"family": "Smith", "given": "J"},
                 {"family": "Doe", "given": "A"}],
        year=2020,
        journal="J of Stuff",
        doi="10.1/abc",
        publisher=None,
    )
    assert out.startswith("@article{smith2020x,")
    assert "author = {Smith, J and Doe, A}" in out
    assert "title = {A Study}" in out
    assert "journal = {J of Stuff}" in out
    assert "doi = {10.1/abc}" in out
    assert out.endswith("}")


def test_render_bibtex_escapes_amp():
    out = render_bibtex(
        key="x2020y", entry_type="misc",
        title="R&D Strategy", authors=[], year=2020,
    )
    assert r"title = {R\&D Strategy}" in out


def test_render_apa_two_authors():
    out = render_apa(
        title="The Study", authors=[
            {"family": "Smith", "given": "John"},
            {"family": "Doe", "given": "Jane Q."},
        ],
        year=2020, journal="J of Stuff", doi="10.1/abc",
    )
    assert "Smith, J., & Doe, J. Q." in out
    assert "(2020)" in out
    assert "https://doi.org/10.1/abc" in out


def test_render_apa_no_year():
    out = render_apa(title="X", authors=[{"family": "S"}], year=None)
    assert "(n.d.)" in out


# ─── Service ───────────────────────────────────────────────────────


def _make_paper(session, **kw):
    defaults = dict(stem="s", status="analyzed", source="root",
                    title="A Study", year=2020,
                    authors_json=[{"family": "Smith", "given": "J"}],
                    doi="10.1/abc")
    defaults.update(kw)
    p = models.Paper(**defaults)
    session.add(p)
    session.flush()
    return p


def test_generate_creates_citation_row(session):
    p = _make_paper(session)
    cite = CitationService().generate(session, p)
    assert cite.id is not None
    assert cite.paper_id == p.id
    assert cite.citation_key == "smith2020study"
    assert cite.bibtex.startswith("@misc{")  # 没 journal → misc
    assert "Smith, J." in cite.apa


def test_generate_is_idempotent_without_refresh(session):
    p = _make_paper(session)
    svc = CitationService()
    c1 = svc.generate(session, p)
    c2 = svc.generate(session, p)
    assert c1.id == c2.id


def test_generate_refresh_updates_in_place(session):
    p = _make_paper(session)
    svc = CitationService()
    c1 = svc.generate(session, p)
    p.title = "A New Title"
    session.flush()
    c2 = svc.generate(session, p, refresh=True)
    assert c1.id == c2.id
    assert "A New Title" in c2.bibtex


def test_generate_with_journal_uses_article_entry(session):
    j = models.Journal(issn="0025-1909", name="Management Science",
                       publisher="INFORMS")
    session.add(j); session.flush()
    p = _make_paper(session)
    p.journal_id = j.id
    session.flush()
    # reload paper to attach journal
    session.refresh(p)
    cite = CitationService().generate(session, p)
    assert cite.bibtex.startswith("@article{")
    assert "journal = {Management Science}" in cite.bibtex


def test_generate_falls_back_to_openalex(session, monkeypatch):
    """paper 缺 title/authors 但有 doi 时，应 OpenAlex 补全。"""
    p = _make_paper(session, title="", authors_json=None, year=None)

    class FakeResp:
        status_code = 200
        def json(self):
            return {
                "title": "Recovered Title",
                "publication_year": 2019,
                "authorships": [{"author": {"display_name": "Alice Wonder"}}],
                "primary_location": {"source": {"display_name": "Some Journal"}},
            }
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: FakeResp())

    cite = CitationService().generate(session, p)
    assert "Recovered Title" in cite.bibtex
    assert "Wonder" in cite.bibtex
    assert "2019" in cite.bibtex


def test_bibtex_for_all_concatenates(session):
    p1 = _make_paper(session, stem="a", doi="10.1/a", title="One")
    p2 = _make_paper(session, stem="b", doi="10.1/b", title="Two")
    svc = CitationService()
    svc.generate(session, p1)
    svc.generate(session, p2)
    blob = svc.bibtex_for_all(session)
    assert "One" in blob and "Two" in blob
    # 两条之间用空行隔开
    assert "\n\n@" in blob


def test_slug_strips_non_ascii():
    assert slug_for_key("O'Brien-Smith") == "obriensmith"
    assert slug_for_key("") == ""
