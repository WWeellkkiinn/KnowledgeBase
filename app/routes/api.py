"""REST API blueprint（M1.5 最小只读集）。"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select

from database import models

bp = Blueprint("api", __name__)


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
        "added_at": p.added_at.isoformat() if p.added_at else None,
        "analyzed_at": p.analyzed_at.isoformat() if p.analyzed_at else None,
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
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
    }


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@bp.get("/papers")
def list_papers():
    status = request.args.get("status")
    source = request.args.get("source")
    try:
        limit = min(int(request.args.get("limit", 200)), 1000)
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
    p = g.db.get(models.Paper, paper_id)
    if p is None:
        return jsonify({"error": "not found"}), 404
    edges_out = g.db.execute(
        select(models.Edge).where(models.Edge.from_paper_id == paper_id)
    ).scalars().all()
    edges_in = g.db.execute(
        select(models.Edge).where(models.Edge.to_paper_id == paper_id)
    ).scalars().all()
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
        limit = min(int(request.args.get("limit", 100)), 500)
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
