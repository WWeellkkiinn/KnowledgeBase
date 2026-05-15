"""REST API blueprint（M1.5 最小只读集）。"""
from __future__ import annotations

import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path as _Path

from flask import Blueprint, Response, abort, g, jsonify, request, stream_with_context
from sqlalchemy import delete, func, select, update

from database import models


_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _require_token(scope: str = "write") -> None:
    """检查 X-KB-Token header（仅当对应 KB_API_TOKEN_* 环境变量配置时启用）。

    scope=write：优先读 KB_API_TOKEN_WRITE，未设时 fallback KB_API_TOKEN（统一令牌），
                  仍未设则放行（本地开发默认）。
    """
    expected = (
        os.environ.get(f"KB_API_TOKEN_{scope.upper()}")
        or os.environ.get("KB_API_TOKEN")
    )
    if not expected:
        return  # 未配置 = 本地开发模式，不强制
    provided = request.headers.get("X-KB-Token") or request.args.get("token") or ""
    if provided != expected:
        abort(401, description="invalid or missing API token")

_log = logging.getLogger(__name__)

bp = Blueprint("api", __name__)


@bp.before_request
def _gate_writes() -> None:
    """全局写操作鉴权：所有 POST/PUT/PATCH/DELETE 都需要 token（若已配置）。"""
    if request.method in _WRITE_METHODS:
        _require_token("write")


# 项目根目录（app/routes/api.py → app/routes/ → app/ → 项目根）
_BASE_DIR = _Path(__file__).parent.parent.parent.resolve()
_INSIGHT_MAX_BYTES = 512 * 1024  # 512 KB，防止超大文件打爆内存

# 文件名清洗：仅允许 ASCII 字母数字 + 常见安全字符。剥所有控制字符（含 \r \n）
# 与引号，防止 Content-Disposition header 注入（HTTP response splitting）。
_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe_filename(stem: str, ext: str) -> str:
    cleaned = _FILENAME_SAFE.sub("_", (stem or "").strip())[:120] or "file"
    return f"{cleaned}{ext}"


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
        "abstract": p.abstract,
        "authors_json": p.authors_json,
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
        "is_core": bool(p.is_core),
        "tags": p.tags,
        "ai_summary": p.ai_summary,
        "ai_analyzed_at": _iso_utc(p.ai_analyzed_at),
    }
    if include_journal:
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
    tier = request.args.get("tier", "core")
    if tier not in ("core", "stub", "all"):
        return jsonify({"error": "tier must be core, stub, or all"}), 400
    try:
        limit = max(1, min(int(request.args.get("limit", 200)), 1000))
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        return jsonify({"error": "invalid pagination"}), 400

    from sqlalchemy.orm import joinedload
    stmt = select(models.Paper).options(joinedload(models.Paper.journal)).order_by(models.Paper.id.asc())
    if tier == "core":
        stmt = stmt.where(models.Paper.is_core.is_(True))
    elif tier == "stub":
        stmt = stmt.where(models.Paper.is_core.is_(False))
    if status:
        stmt = stmt.where(models.Paper.status == status)
    if source:
        stmt = stmt.where(models.Paper.source == source)
    stmt = stmt.limit(limit).offset(offset)

    rows = g.db.execute(stmt).scalars().all()
    return jsonify({"items": [_paper_to_dict(p, include_journal=True) for p in rows], "limit": limit, "offset": offset})


@bp.get("/papers/stats")
def papers_stats():
    """轻量聚合：库内 paper 总数 + 已分析数，供 Dashboard 用，
    避免前端为算计数把 500 条 papers 全拉回来。"""
    total = g.db.execute(select(func.count()).select_from(models.Paper)).scalar_one()
    analyzed = g.db.execute(
        select(func.count()).select_from(models.Paper)
        .where(models.Paper.status == "analyzed")
    ).scalar_one()
    return jsonify({"total": int(total), "analyzed": int(analyzed)})


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


@bp.get("/papers/<int:paper_id>/insight")
def paper_insight(paper_id: int):
    p = g.db.get(models.Paper, paper_id)
    if p is None:
        return jsonify({"error": "not found"}), 404
    if not p.insight_path:
        return jsonify({"content": None})
    path = (_BASE_DIR / p.insight_path).resolve()
    # 路径遍历防护：确保解析后路径仍在项目根目录内
    if not path.is_relative_to(_BASE_DIR):
        _log.warning("insight path traversal attempt: paper=%d path=%s", paper_id, p.insight_path)
        return jsonify({"error": "forbidden"}), 403
    try:
        if not path.exists():
            return jsonify({"content": None})
        if path.stat().st_size > _INSIGHT_MAX_BYTES:
            _log.warning("insight file too large: paper=%d size=%d", paper_id, path.stat().st_size)
            return jsonify({"content": None})
        content = path.read_text("utf-8")
    except (PermissionError, UnicodeDecodeError, OSError) as exc:
        _log.warning("insight read failed: paper=%d err=%s", paper_id, exc)
        return jsonify({"content": None})
    return jsonify({"content": content})


@bp.post("/papers/<int:paper_id>/forward-track")
def forward_track(paper_id: int):
    """触发前向追踪。可选 body：`{"refresh": true, "limit": 100}`。

    依赖论文有 DOI；无 DOI 返回 422。命中缓存（7 天内）则返回 `cached: true`，
    传 `refresh=true` 可强制重查。
    """
    if request.content_length is not None and request.content_length > 1024:
        return jsonify({"error": "request body too large"}), 413

    p = g.db.get(models.Paper, paper_id)
    if p is None:
        return jsonify({"error": "not found"}), 404
    if not p.doi:
        return jsonify({"error": "paper has no DOI"}), 422

    body = request.get_json(silent=True) or {}
    refresh = bool(body.get("refresh", False))
    raw_limit = body.get("limit")
    if raw_limit is None:
        limit = None
    else:
        try:
            limit = max(1, min(int(raw_limit), 10000))
        except (TypeError, ValueError):
            return jsonify({"error": "invalid limit"}), 400

    from services import ForwardTrackService
    try:
        result = ForwardTrackService(db_session=g.db).track(
            p.doi, refresh=refresh, limit=limit, from_paper_id=paper_id
        )
        g.db.commit()
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        g.db.rollback()
        _log.exception("forward-track failed")
        return jsonify({"error": "forward-track failed"}), 502


@bp.post("/papers/<int:paper_id>/backward-track")
def backward_track(paper_id: int):
    """触发后向追踪：查这篇论文引用了哪些论文。可选 body：`{"refresh": true, "limit": 100}`。

    依赖论文有 DOI；无 DOI 返回 422。7 天缓存，`refresh=true` 强制重查。
    """
    if request.content_length is not None and request.content_length > 1024:
        return jsonify({"error": "request body too large"}), 413

    p = g.db.get(models.Paper, paper_id)
    if p is None:
        return jsonify({"error": "not found"}), 404
    if not p.doi:
        return jsonify({"error": "paper has no DOI"}), 422

    body = request.get_json(silent=True) or {}
    refresh = bool(body.get("refresh", False))
    raw_limit = body.get("limit")
    if raw_limit is None:
        limit = None
    else:
        try:
            limit = max(1, min(int(raw_limit), 10000))
        except (TypeError, ValueError):
            return jsonify({"error": "invalid limit"}), 400

    from services import BackwardTrackService
    try:
        result = BackwardTrackService(db_session=g.db).track(
            p.doi, refresh=refresh, limit=limit, from_paper_id=paper_id
        )
        g.db.commit()
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        g.db.rollback()
        _log.exception("backward-track failed")
        return jsonify({"error": "backward-track failed"}), 502


@bp.post("/papers/<int:paper_id>/promote")
def promote_paper(paper_id: int):
    """将 stub 论文晋升为核心论文（幂等：已是核心时直接返回）。"""
    from sqlalchemy.orm import joinedload as _jl
    p = g.db.execute(
        select(models.Paper).options(_jl(models.Paper.journal))
        .where(models.Paper.id == paper_id)
    ).scalar_one_or_none()
    if p is None:
        return jsonify({"error": "not found"}), 404
    if not p.is_core:
        p.is_core = True
        try:
            g.db.commit()
        except Exception:
            g.db.rollback()
            _log.exception("promote_paper failed paper_id=%d", paper_id)
            return jsonify({"error": "promote failed"}), 502
    return jsonify(_paper_to_dict(p, include_journal=True))


@bp.post("/papers/<int:paper_id>/ai-analyze")
def ai_analyze_paper(paper_id: int):
    """触发单篇论文的 AI 打标签 + 精炼（F1+F2）。"""
    p = g.db.get(models.Paper, paper_id)
    if p is None:
        return jsonify({"error": "not found"}), 404
    if not p.abstract:
        return jsonify({"error": "no abstract"}), 422
    from services.ai_service import analyze_paper
    try:
        result = analyze_paper(p.title or "", p.abstract)
    except Exception:
        _log.exception("ai_analyze_paper analysis error paper_id=%d", paper_id)
        return jsonify({"error": "analysis failed"}), 502
    if not result:
        return jsonify({"error": "analysis failed"}), 502
    tags = result.get("tags")
    p.tags = tags if isinstance(tags, list) else []
    p.ai_summary = {k: v for k, v in result.items() if k != "tags"}
    p.ai_analyzed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        g.db.commit()
    except Exception:
        g.db.rollback()
        _log.exception("ai_analyze_paper commit failed paper_id=%d", paper_id)
        return jsonify({"error": "db error"}), 502
    return jsonify(_paper_to_dict(p, include_journal=True))


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
    # 删除前若有未读 inbox 项，要求显式 ?force=1 确认（避免静默丢未读通知）
    sub = g.db.get(models.Subscription, sub_id)
    if sub is None:
        return jsonify({"error": "not found"}), 404
    unread = g.db.execute(
        select(models.SubscriptionResult.id)
        .where(models.SubscriptionResult.subscription_id == sub_id)
        .where(models.SubscriptionResult.notified.is_(False))
        .limit(1)
    ).first()
    if unread is not None and request.args.get("force") not in ("1", "true", "yes"):
        return jsonify({
            "error": "subscription has unread results",
            "hint": "DELETE ?force=1 to confirm",
        }), 409
    SubscriptionService.delete(g.db, sub_id)
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
         "Content-Disposition": f'attachment; filename="{_safe_filename(p.stem, ".bib")}"'},
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


# ─── M3.5 跨论文综述 SSE 流 ───────────────────────────────────────

import json as _json  # 模块顶部 import 避免每次请求做局部 import
import threading as _threading
from services import ReviewService as _ReviewService

# 全局重入保护：同一进程内最多 _REVIEW_MAX_INFLIGHT 个综述流并发，
# 防止用户连点导致 LLM 资源耗尽（review skill C2/X3 审查发现）。
_REVIEW_MAX_INFLIGHT = 2
_review_inflight = 0
_review_lock = _threading.Lock()


def _try_acquire_review_slot() -> bool:
    global _review_inflight
    with _review_lock:
        if _review_inflight >= _REVIEW_MAX_INFLIGHT:
            return False
        _review_inflight += 1
        return True


def _release_review_slot() -> None:
    global _review_inflight
    with _review_lock:
        _review_inflight = max(0, _review_inflight - 1)


@bp.post("/reviews")
def create_review():
    """触发综述生成。SSE 流式响应，事件名 `chunk` / `done` / `error`。

    body: {"paper_ids": [int, ...], "focus": str}
    """
    body = request.get_json(silent=True) or {}
    raw_ids = body.get("paper_ids") or []
    if not isinstance(raw_ids, list) or not raw_ids:
        return jsonify({"error": "paper_ids required"}), 400
    try:
        paper_ids = [int(x) for x in raw_ids][:50]  # 上限 50 篇，防止 LLM 上下文爆
    except (TypeError, ValueError):
        return jsonify({"error": "paper_ids must be ints"}), 400
    focus = str(body.get("focus") or "研究方法")[:200]

    if not _try_acquire_review_slot():
        return jsonify({"error": "too many concurrent reviews; try again later"}), 429

    svc = _ReviewService()

    def _emit_error(msg: str) -> str:
        # SSE data 字段不允许裸 \n（spec 要求拆多行 data:）。
        # JSON.stringify 已将 \n 转义为 "\\n"，但保险起见再保证单行。
        return f"event: error\ndata: {_json.dumps({'error': msg})}\n\n"

    def sse():
        try:
            for chunk in svc.generate_stream(g.db, paper_ids, focus=focus):
                yield f"event: chunk\ndata: {_json.dumps(chunk, ensure_ascii=False)}\n\n"
            yield "event: done\ndata: {}\n\n"
        except Exception:
            # 详细异常只落日志，不回显客户端（与 forward-track 策略一致）。
            _log.exception("review stream failed")
            yield _emit_error("review stream failed")
        finally:
            _release_review_slot()

    return Response(
        stream_with_context(sse()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁 nginx 缓冲（如果有反代）
        },
    )


# ─── M3.4 网络图全图（薄壳：纯只读聚合） ────────────────────────────


@bp.get("/network")
def get_network():
    """返回 Cytoscape 渲染所需的 {nodes, edges, total}。

    只渲染核心论文（is_core=True）节点，节点携带 authors_json + citation_count。
    edges 只保留两端均为核心论文的边。
    """
    try:
        limit = max(1, min(int(request.args.get("limit", 1000)), 2000))
    except ValueError:
        return jsonify({"error": "invalid pagination"}), 400

    total = g.db.execute(
        select(func.count()).select_from(models.Paper)
        .where(models.Paper.is_core.is_(True))
    ).scalar_one()

    papers = g.db.execute(
        select(models.Paper)
        .where(models.Paper.is_core.is_(True))
        .order_by(models.Paper.id.asc()).limit(limit)
    ).scalars().all()
    paper_id_set: set[int] = {p.id for p in papers}
    paper_year: dict[int, int | None] = {p.id: p.year for p in papers}

    journal_ids = [pid for pid in {p.journal_id for p in papers} if pid is not None]
    journal_tier: dict[int, int | None] = {}
    _CHUNK = 800
    for i in range(0, len(journal_ids), _CHUNK):
        batch = journal_ids[i:i + _CHUNK]
        if not batch:
            continue
        for j in g.db.execute(
            select(models.Journal.id, models.Journal.quality_tier)
            .where(models.Journal.id.in_(batch))
        ).all():
            journal_tier[j.id] = j.quality_tier

    # 被引量：分批查询避免超 SQLite 999 参数上限
    citation_counts: dict[int, int] = {}
    if paper_id_set:
        id_list = list(paper_id_set)
        for i in range(0, len(id_list), _CHUNK):
            batch = id_list[i:i + _CHUNK]
            for row in g.db.execute(
                select(models.Edge.from_paper_id, func.count().label("cnt"))
                .where(models.Edge.from_paper_id.in_(batch))
                .where(models.Edge.direction == "forward")
                .group_by(models.Edge.from_paper_id)
            ).all():
                citation_counts[row.from_paper_id] = row.cnt

    # 边方向语义：
    #   backward: from_paper_id 引用 to_paper_id（from 是引用者），图方向 from→to
    #   forward:  to_paper_id 引用 from_paper_id（to 是引用者），图方向 to→from（需反转）
    # seen_pairs 在规范化后去重，消除 backward+forward 表示同一引用关系的重复边
    # WHERE 子句预过滤：只取至少一端在核心论文集内的边，避免全表扫描（21 个 id 远低于 SQLite 999 参数上限）
    id_list = list(paper_id_set)
    edges_out: list[dict] = []
    seen_pairs: set[tuple[int, int]] = set()
    for row in g.db.execute(
        select(models.Edge.id, models.Edge.from_paper_id, models.Edge.to_paper_id, models.Edge.direction)
        .where(
            (models.Edge.from_paper_id.in_(id_list)) | (models.Edge.to_paper_id.in_(id_list))
        )
    ):
        f, t = row.from_paper_id, row.to_paper_id
        if row.direction == "forward":
            f, t = t, f  # forward 边：引用者是 to，规范化为 citing→cited
        elif row.direction != "backward":
            continue  # 跳过未知 direction 值，避免脏数据污染图
        if f == t:  # 跳过自环
            continue
        if f not in paper_id_set or t not in paper_id_set:
            continue
        # 年份过滤：引用者年份早于被引者则为时序不可能的边（forthcoming 误判），跳过
        # 任一端 year=NULL 时跳过过滤，保留该边
        fy, ty = paper_year.get(f), paper_year.get(t)
        if fy is not None and ty is not None and fy < ty:
            continue
        if (f, t) in seen_pairs:
            continue
        seen_pairs.add((f, t))
        edges_out.append({"id": row.id, "from": f, "to": t})

    return jsonify({
        "nodes": [
            {
                "id": p.id,
                "stem": p.stem,
                "title": p.title,
                "year": p.year,
                "authors_json": p.authors_json,
                "status": p.status,
                "source": p.source,
                "quality_tier": journal_tier.get(p.journal_id) if p.journal_id is not None else None,
                "citation_count": citation_counts.get(p.id, 0),
            }
            for p in papers
        ],
        "edges": edges_out,
        "total": total,
        "truncated": total > len(papers),
    })


# ─── M4.3 失败诊断面板 ───────────────────────────────────────────────

import os as _os


def _categorize_reason(reason: str) -> str:
    r = reason.lower()
    # 用 "HTTP 4xx" 前缀而非裸数字，避免 "4031"/"14032" 等子串误匹配（C1 审查）
    if "http 403" in r or "http 401" in r:
        return "paywalled"
    if re.search(r"http [45]\d\d", r):
        return "http_error"
    if "not a pdf" in r or "content-type" in r:
        return "not_a_pdf"
    if "timeout" in r or "browser fail" in r:
        return "browser_timeout"
    if "no pdf" in r or "not found" in r:
        return "no_pdf_found"
    return "other"


def _parse_refs_failed(path: _Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    items = []
    for section in re.split(r"\n## \[", text)[1:]:
        lines = section.strip().splitlines()
        m = re.match(r"(\d+)\](.+)", lines[0]) if lines else None
        if not m:
            continue
        ref_index = int(m.group(1))
        header_rest = m.group(2).strip()
        doi = pdf_url = reason = ""
        for line in lines[1:]:
            line = line.strip()
            if line.startswith("- doi:"):
                doi = line[6:].strip()
            elif line.startswith("- pdf_url:"):
                pdf_url = line[10:].strip()
            elif line.startswith("- reason:"):
                reason = line[9:].strip()
        items.append({
            "ref_index": ref_index,
            "header": header_rest,
            "doi": doi,
            "pdf_url": pdf_url,
            "reason": reason,
            "category": _categorize_reason(reason),
        })
    return items


@bp.get("/failures")
def get_failures():
    """扫描所有 papers/*/refs_failed.md，聚合失败条目及分类统计。"""
    papers_root = _Path(_os.environ.get("PAPERS_DIR", "papers")).resolve()
    # 防止 PAPERS_DIR 被设为项目外路径（C3 审查路径遍历）
    try:
        papers_root.relative_to(_BASE_DIR)
    except ValueError:
        return jsonify({"error": "PAPERS_DIR must be inside project root"}), 400

    items: list[dict] = []
    # 只取 stem/id 两列，避免全量 Paper 行进内存（C2/X2 审查）
    paper_map: dict[str, int] = {
        stem: pid
        for stem, pid in g.db.execute(
            select(models.Paper.stem, models.Paper.id)
        ).all()
    }

    for failed_file in sorted(papers_root.glob("*/refs_failed.md")):
        stem = failed_file.parent.name
        paper_id = paper_map.get(stem)
        for entry in _parse_refs_failed(failed_file):
            items.append({**entry, "stem": stem, "paper_id": paper_id})

    by_category: dict[str, int] = {}
    for it in items:
        cat = it["category"]
        by_category[cat] = by_category.get(cat, 0) + 1

    return jsonify({"total": len(items), "by_category": by_category, "items": items})


# ─── 批量操作 ─────────────────────────────────────────────────────────


def _parse_paper_ids(raw_ids: list) -> list[int]:
    """验证并去重 ids：正整数，排除 bool，上限 200。"""
    seen: set[int] = set()
    result: list[int] = []
    for x in raw_ids[:200]:
        if isinstance(x, bool) or not isinstance(x, int) or x <= 0:
            raise ValueError(f"invalid id: {x!r}")
        if x not in seen:
            seen.add(x)
            result.append(x)
    return result


@bp.delete("/papers/batch")
def delete_papers_batch():
    """批量删除论文，级联删除关联的 edges 和 citations。body: {"ids": [int]}"""
    if request.content_length is not None and request.content_length > 16 * 1024:
        return jsonify({"error": "request body too large"}), 413
    body = request.get_json(silent=True) or {}
    raw_ids = body.get("ids", [])
    if not isinstance(raw_ids, list) or not raw_ids:
        return jsonify({"error": "ids required"}), 400
    try:
        ids = _parse_paper_ids(raw_ids)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    try:
        g.db.execute(delete(models.Edge).where(
            (models.Edge.from_paper_id.in_(ids)) | (models.Edge.to_paper_id.in_(ids))
        ))
        g.db.execute(delete(models.Citation).where(models.Citation.paper_id.in_(ids)))
        result = g.db.execute(delete(models.Paper).where(models.Paper.id.in_(ids)))
        g.db.commit()
        return jsonify({"deleted": result.rowcount})
    except Exception:
        g.db.rollback()
        _log.exception("delete_papers_batch failed")
        return jsonify({"error": "delete failed"}), 502


@bp.patch("/papers/batch/tier")
def move_papers_batch():
    """批量移动论文层级。body: {"ids": [int], "is_core": bool}"""
    if request.content_length is not None and request.content_length > 16 * 1024:
        return jsonify({"error": "request body too large"}), 413
    body = request.get_json(silent=True) or {}
    raw_ids = body.get("ids", [])
    is_core = body.get("is_core")
    if not isinstance(raw_ids, list) or not raw_ids:
        return jsonify({"error": "ids required"}), 400
    if not isinstance(is_core, bool):
        return jsonify({"error": "is_core must be bool"}), 400
    try:
        ids = _parse_paper_ids(raw_ids)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    try:
        result = g.db.execute(
            update(models.Paper).where(models.Paper.id.in_(ids)).values(is_core=is_core)
        )
        g.db.commit()
        return jsonify({"updated": result.rowcount})
    except Exception:
        g.db.rollback()
        _log.exception("move_papers_batch failed")
        return jsonify({"error": "move failed"}), 502


@bp.post("/digest/send")
def send_digest_now():
    """手动触发邮件日报（F3）。
    ?all=1    发送全库（有摘要的）论文，否则仅过去 24h
    ?core=1   仅扫核心库论文
    ?test=1   快速测试：跳过 AI 直接拼前 5 篇核心论文发邮件，~5 秒（同步）
    ?async=1  在后台线程异步执行，立即返回 {accepted: true}
    """
    from services.digest_service import send_digest

    test_mode = request.args.get("test") == "1"
    if test_mode:
        kwargs = dict(hours_back=0, core_only=True, skip_ai=True, limit=5)
    else:
        kwargs = dict(
            hours_back=0 if request.args.get("all") == "1" else 24,
            core_only=request.args.get("core") == "1",
        )

    if request.args.get("async") == "1" and not test_mode:
        def _bg():
            from database import SessionLocal
            session = SessionLocal()
            try:
                send_digest(session, **kwargs)
            except Exception:
                _log.exception("async send_digest failed")
            finally:
                session.close()
        threading.Thread(target=_bg, name="digest-async", daemon=True).start()
        return jsonify({"accepted": True})

    try:
        return jsonify(send_digest(g.db, **kwargs))
    except Exception as exc:
        _log.exception("send_digest_now failed: %s", type(exc).__name__)
        return jsonify({"error": "digest failed"}), 502
