"""graph_writer.py — 把追踪结果写入 papers + edges 表。

供 ForwardTrackService 和 BackwardTrackService 调用，不含缓存或 HTTP 逻辑。
写入采用"upsert"语义：已存在的论文/边跳过，不报错也不重复插入。
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import models

_log = logging.getLogger(__name__)

# stem 长度上限，避免文件系统问题
_STEM_MAX = 120
_AUTHORS_MAX = 500


def _doi_to_stem(doi: str) -> str:
    """把 DOI 转成文件系统安全的 stem（不含路径分隔符）。"""
    return doi.replace("/", "_").replace(".", "_").replace(":", "_")[:_STEM_MAX]


def upsert_paper(
    session: Session,
    doi: str,
    title: Optional[str],
    year: Optional[int],
    authors: Optional[str],
    source: str,
) -> Optional[models.Paper]:
    """按 DOI 查找或创建 stub Paper。DOI 为空时尝试按标题查询，仍空则返回 None。"""
    if not doi and title:
        try:
            from services.doi_resolver import resolve_doi
            doi = resolve_doi(title) or ""
        except Exception as exc:
            _log.debug("[graph_writer] doi_resolver failed title=%r err=%s", title[:60], exc)
    if not doi:
        return None

    existing = session.execute(
        select(models.Paper).where(models.Paper.doi == doi)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    stem = _doi_to_stem(doi)
    # stem 也要唯一——若已被占用（罕见冲突）加后缀
    if session.execute(
        select(models.Paper.id).where(models.Paper.stem == stem)
    ).first() is not None:
        stem = stem[:110] + "_" + doi[-8:].replace("/", "_")

    paper = models.Paper(
        stem=stem,
        doi=doi,
        title=title or None,
        authors_json=[a for a in authors[:_AUTHORS_MAX].split(", ") if a] if authors else None,
        year=year,
        status="pending",
        source=source,
    )
    try:
        with session.begin_nested():
            session.add(paper)
            session.flush()
    except IntegrityError:
        # 并发竞态：另一个请求刚好也插了同一 DOI，重查
        existing = session.execute(
            select(models.Paper).where(models.Paper.doi == doi)
        ).scalar_one_or_none()
        return existing
    return paper


def _edge_exists(session: Session, from_id: int, to_id: int, direction: str) -> bool:
    return session.execute(
        select(models.Edge.id)
        .where(models.Edge.from_paper_id == from_id)
        .where(models.Edge.to_paper_id == to_id)
        .where(models.Edge.direction == direction)
        .limit(1)
    ).first() is not None


_VENUE_NAME_MAX = 512
_VENUE_ISSN_MAX = 16


def _attach_journal_if_any(session: Session, paper, item: dict) -> None:
    """若 item 带有 venue 信息且 paper 尚未关联期刊，顺手写入期刊。"""
    if paper.journal_id is not None:
        return
    venue_name = (item.get("venue_name") or "").strip()[:_VENUE_NAME_MAX]
    venue_issn = (item.get("venue_issn") or "").strip()[:_VENUE_ISSN_MAX]
    if not venue_name and not venue_issn:
        return
    try:
        from services.journal_service import JournalService
        meta = {
            "name": venue_name,
            "issn": venue_issn,
            "source_dataset": "openalex",
        }
        JournalService().attach_to_paper(session, paper, meta=meta)
    except Exception as exc:
        _log.warning("[graph_writer] journal attach failed paper_id=%s err=%s", paper.id, exc)


def write_tracking_results(
    session: Session,
    from_paper_id: int,
    papers_data: list[dict],
    direction: str,
) -> int:
    """把追踪结果批量写入 papers + edges 表，返回新增边数。

    direction="backward": 被查论文 → 它引用的论文（后向），stub source="ref"
    direction="forward":  被查论文 ← 引用它的论文（前向），stub source="forward"
    """
    stub_source = "ref" if direction == "backward" else "forward"
    dois = [(item.get("doi") or "").strip() for item in papers_data]
    dois = [doi for doi in dois if doi]
    existing_by_doi = {
        paper.doi: paper
        for paper in session.execute(
            select(models.Paper).where(models.Paper.doi.in_(dois))
        ).scalars()
        if paper.doi
    }
    existing_to_ids = set(session.execute(
        select(models.Edge.to_paper_id)
        .where(models.Edge.from_paper_id == from_paper_id)
        .where(models.Edge.direction == direction)
    ).scalars())
    new_edges = []

    for item in papers_data:
        doi = (item.get("doi") or "").strip()
        if not doi:
            continue  # 无 DOI 无法去重，跳过

        paper = existing_by_doi.get(doi)
        if paper is None:
            paper = models.Paper(
                stem=_doi_to_stem(doi),
                doi=doi,
                title=item.get("title") or None,
                authors_json=[a for a in item["authors"][:_AUTHORS_MAX].split(", ") if a] if item.get("authors") else None,
                year=item.get("year"),
                status="pending",
                source=stub_source,
            )
            try:
                with session.begin_nested():
                    session.add(paper)
                    session.flush()
            except IntegrityError:
                paper = session.execute(
                    select(models.Paper).where(models.Paper.doi == doi)
                ).scalar_one_or_none()
            if paper is not None:
                existing_by_doi[doi] = paper

        if paper is None or paper.id is None:
            continue

        _attach_journal_if_any(session, paper, item)

        to_id = paper.id
        if to_id in existing_to_ids:
            continue

        new_edges.append(models.Edge(
            from_paper_id=from_paper_id,
            to_paper_id=to_id,
            direction=direction,
            ref_index=None,
            ref_title=item.get("title"),
        ))
        existing_to_ids.add(to_id)

    added = len(new_edges)
    if new_edges:
        try:
            with session.begin_nested():
                session.add_all(new_edges)
                session.flush()
        except IntegrityError:
            added = 0

    _log.info("[graph_writer] direction=%s from=%d added=%d edges", direction, from_paper_id, added)
    return added
