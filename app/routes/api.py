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


def _journal_to_dict(j: models.Journal) -> dict:
    return {
        "id": j.id,
        "issn": j.issn,
        "name": j.name,
        "publisher": j.publisher,
        "quality_tier": j.quality_tier,
        "is_predatory": bool(j.is_predatory),
        "oa_status": j.oa_status,
    }


def _paper_to_dict(p: models.Paper, *, include_journal: bool = False) -> dict:
    out = {
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
        "journal_id": p.journal_id,
        "added_at": _iso_utc(p.added_at),
        "analyzed_at": _iso_utc(p.analyzed_at),
    }
    if include_journal:
        # journal 关系按 lazy="select"，详情页才取，列表页不取避免 N+1
        out["journal"] = _journal_to_dict(p.journal) if p.journal else None
    return out


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
        "paper": _paper_to_dict(p, include_journal=True),
        "edges_out": [_edge_to_dict(e) for e in edges_out],
        "edges_in": [_edge_to_dict(e) for e in edges_in],
    })


@bp.post("/papers/<int:paper_id>/forward-track")
def forward_track(paper_id: int):
    """触发前向追踪。可选 body：`{"refresh": true, "limit": 100}`。

    依赖论文有 DOI；无 DOI 返回 422。命中缓存（7 天内）则返回 `cached: true`，
    传 `refresh=true` 可强制重查。
    """
    p = g.db.get(models.Paper, paper_id)
    if p is None:
        return jsonify({"error": "not found"}), 404
    if not p.doi:
        return jsonify({"error": "paper has no DOI"}), 422

    body = request.get_json(silent=True) or {}
    refresh = bool(body.get("refresh", False))
    try:
        limit = max(1, min(int(body.get("limit", 100)), 200))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid limit"}), 400

    from services import ForwardTrackService
    try:
        # 用请求 session 而非自建：与 before_request 的 g.db 共享事务
        result = ForwardTrackService(db_session=g.db).track(
            p.doi, refresh=refresh, limit=limit
        )
        g.db.commit()
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        g.db.rollback()
        return jsonify({"error": "forward-track failed", "detail": str(e)}), 502


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


# ─── M2.4 订阅 CRUD + inbox ────────────────────────────────────────


def _sub_to_dict(s: models.Subscription) -> dict:
    return {
        "id": s.id,
        "type": s.type,
        "target": s.target_json,
        "cron_expr": s.cron_expr,
        "active": bool(s.active),
        "last_run_at": _iso_utc(s.last_run_at),
        "next_run_at": _iso_utc(s.next_run_at),
    }


def _result_to_dict(r: models.SubscriptionResult) -> dict:
    return {
        "id": r.id,
        "subscription_id": r.subscription_id,
        "paper_id": r.paper_id,
        "metadata": r.raw_metadata_json,
        "notified": bool(r.notified),
        "found_at": _iso_utc(r.found_at),
    }


@bp.get("/subscriptions")
def list_subscriptions():
    from services import SubscriptionService
    active = request.args.get("active")
    only_active = active in ("1", "true", "yes")
    rows = SubscriptionService.list_all(g.db, active_only=only_active)
    return jsonify({"items": [_sub_to_dict(s) for s in rows]})


@bp.post("/subscriptions")
def create_subscription():
    from services import SubscriptionService
    body = request.get_json(silent=True) or {}
    try:
        sub = SubscriptionService().create(
            g.db,
            type=body.get("type", ""),
            target=body.get("target", {}),
            cron_expr=body.get("cron_expr", "every 7d"),
            active=bool(body.get("active", True)),
        )
        g.db.commit()
        return jsonify(_sub_to_dict(sub)), 201
    except ValueError as e:
        g.db.rollback()
        return jsonify({"error": str(e)}), 400


@bp.patch("/subscriptions/<int:sub_id>")
def update_subscription(sub_id: int):
    from services import SubscriptionService
    body = request.get_json(silent=True) or {}
    try:
        sub = SubscriptionService.update(
            g.db, sub_id,
            cron_expr=body.get("cron_expr"),
            active=body.get("active"),
            target=body.get("target"),
        )
    except ValueError as e:
        g.db.rollback()
        return jsonify({"error": str(e)}), 400
    if sub is None:
        return jsonify({"error": "not found"}), 404
    g.db.commit()
    return jsonify(_sub_to_dict(sub))


@bp.delete("/subscriptions/<int:sub_id>")
def delete_subscription(sub_id: int):
    from services import SubscriptionService
    ok = SubscriptionService.delete(g.db, sub_id)
    if not ok:
        return jsonify({"error": "not found"}), 404
    g.db.commit()
    return "", 204


@bp.get("/inbox")
def list_inbox():
    """订阅发现的新论文。?unread=1 只看未读。"""
    unread = request.args.get("unread") in ("1", "true", "yes")
    try:
        limit = max(1, min(int(request.args.get("limit", 100)), 500))
    except ValueError:
        return jsonify({"error": "invalid pagination"}), 400
    stmt = select(models.SubscriptionResult).order_by(
        models.SubscriptionResult.found_at.desc()
    )
    if unread:
        stmt = stmt.where(models.SubscriptionResult.notified.is_(False))
    stmt = stmt.limit(limit)
    rows = g.db.execute(stmt).scalars().all()
    return jsonify({"items": [_result_to_dict(r) for r in rows]})


@bp.post("/inbox/<int:result_id>/read")
def mark_inbox_read(result_id: int):
    r = g.db.get(models.SubscriptionResult, result_id)
    if r is None:
        return jsonify({"error": "not found"}), 404
    r.notified = True
    g.db.commit()
    return jsonify(_result_to_dict(r))


# ─── M2.5 BibTeX / APA 导出 ────────────────────────────────────────


@bp.post("/papers/<int:paper_id>/citation")
def generate_citation(paper_id: int):
    """生成或刷新单篇 citation。body 可传 `{"refresh": true}`。"""
    p = g.db.get(models.Paper, paper_id)
    if p is None:
        return jsonify({"error": "not found"}), 404
    refresh = bool((request.get_json(silent=True) or {}).get("refresh", False))
    from services import CitationService
    cite = CitationService().generate(g.db, p, refresh=refresh)
    g.db.commit()
    return jsonify({
        "id": cite.id,
        "paper_id": cite.paper_id,
        "citation_key": cite.citation_key,
        "bibtex": cite.bibtex,
        "apa": cite.apa,
        "refreshed_at": _iso_utc(cite.refreshed_at),
    })


@bp.get("/papers/<int:paper_id>/citations.bib")
def get_paper_bibtex(paper_id: int):
    p = g.db.get(models.Paper, paper_id)
    if p is None:
        return jsonify({"error": "not found"}), 404
    from services import CitationService
    cite = g.db.execute(
        select(models.Citation).where(models.Citation.paper_id == paper_id)
    ).scalar_one_or_none()
    if cite is None:
        cite = CitationService().generate(g.db, p)
        g.db.commit()
    return (
        cite.bibtex or "",
        200,
        {"Content-Type": "application/x-bibtex; charset=utf-8",
         "Content-Disposition": f'attachment; filename="{p.stem}.bib"'},
    )


@bp.get("/citations.bib")
def get_all_bibtex():
    """全库 BibTeX 拼接。只读取已生成的 citations，未生成的跳过。"""
    from services import CitationService
    blob = CitationService().bibtex_for_all(g.db)
    return (
        blob,
        200,
        {"Content-Type": "application/x-bibtex; charset=utf-8",
         "Content-Disposition": 'attachment; filename="kb-citations.bib"'},
    )
