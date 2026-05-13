"""REST API blueprint（M1.5 最小只读集）。"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select

from database import models

bp = Blueprint("api", __name__)


def _iso_utc(dt) -> str | None:
    """序列化 naive UTC datetime 为带 Z 后缀的 ISO8601，避免前端按本地时区误解析。"""
    if dt is None:
        return None
    return dt.isoformat(timespec="seconds") + "Z"


def _paper_to_dict(p: models.Paper) -> dict:
    return {
        "id": p.id,
        "stem": p.stem,
        "title": p.title,
        "year": p.year,
        "doi": p.doi,
        "status": p.status,
        "source": p.source,
        "pdf_path": p.pdf_path,
        "md_path": p.md_path,
        "insight_path": p.insight_path,
        "refs_path": p.refs_path,
        "added_at": _iso_utc(p.added_at),
        "analyzed_at": _iso_utc(p.analyzed_at),
    }


def _edge_to_dict(e: models.Edge) -> dict:
    return {
        "id": e.id,
        "from_paper_id": e.from_paper_id,
        "to_paper_id": e.to_paper_id,
        "direction": e.direction,
        "ref_index": e.ref_index,
        "ref_title": e.ref_title,
    }


def _task_to_dict(t: models.Task) -> dict:
    return {
        "id": t.id,
        "type": t.type,
        "paper_id": t.paper_id,
        "status": t.status,
        "attempt": t.attempt,
        "max_attempts": t.max_attempts,
        "parent_task_id": t.parent_task_id,
        "payload": t.payload_json,
        "error_log": t.error_log,
        "started_at": _iso_utc(t.started_at),
        "finished_at": _iso_utc(t.finished_at),
    }


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@bp.get("/papers")
def list_papers():
    status = request.args.get("status")
    source = request.args.get("source")
    try:
        limit = max(1, min(int(request.args.get("limit", 200)), 1000))
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        return jsonify({"error": "invalid pagination"}), 400

    stmt = select(models.Paper).order_by(models.Paper.id.asc())
    if status:
        stmt = stmt.where(models.Paper.status == status)
    if source:
        stmt = stmt.where(models.Paper.source == source)
    stmt = stmt.limit(limit).offset(offset)

    rows = g.db.execute(stmt).scalars().all()
    return jsonify({"items": [_paper_to_dict(p) for p in rows], "limit": limit, "offset": offset})


@bp.get("/papers/<int:paper_id>")
def get_paper(paper_id: int):
    from sqlalchemy import or_

    p = g.db.get(models.Paper, paper_id)
    if p is None:
        return jsonify({"error": "not found"}), 404
    # 单次查询同时取出 out + in 边，按 from/to 二分到两个列表
    rows = g.db.execute(
        select(models.Edge).where(
            or_(models.Edge.from_paper_id == paper_id,
                models.Edge.to_paper_id == paper_id)
        )
    ).scalars().all()
    edges_out = [e for e in rows if e.from_paper_id == paper_id]
    edges_in = [e for e in rows if e.to_paper_id == paper_id]
    return jsonify({
        "paper": _paper_to_dict(p),
        "edges_out": [_edge_to_dict(e) for e in edges_out],
        "edges_in": [_edge_to_dict(e) for e in edges_in],
    })


@bp.get("/tasks")
def list_tasks():
    status = request.args.get("status")
    type_ = request.args.get("type")
    try:
        limit = max(1, min(int(request.args.get("limit", 100)), 500))
    except ValueError:
        return jsonify({"error": "invalid pagination"}), 400

    stmt = select(models.Task).order_by(models.Task.id.desc())
    if status:
        stmt = stmt.where(models.Task.status == status)
    if type_:
        stmt = stmt.where(models.Task.type == type_)
    stmt = stmt.limit(limit)
    rows = g.db.execute(stmt).scalars().all()
    return jsonify({"items": [_task_to_dict(t) for t in rows]})
