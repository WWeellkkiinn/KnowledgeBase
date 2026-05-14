"""REST API blueprint（M1.5 最小只读集）。"""
from __future__ import annotations

import logging
import re

from flask import Blueprint, Response, g, jsonify, request, stream_with_context
from sqlalchemy import func, select

from database import models

_log = logging.getLogger(__name__)

bp = Blueprint("api", __name__)

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
    try:
        limit = max(1, min(int(body.get("limit", 100)), 200))
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

    - nodes：携带 quality_tier（用于前端按 Tier 着色），N 大时不取 journal 详情
    - edges：用 Python 端 paper_id_set 过滤（避免 SQLite 999 参数上限）
    - total：库内 paper 总数，供前端判断是否截断
    """
    try:
        limit = max(1, min(int(request.args.get("limit", 1000)), 2000))
    except ValueError:
        return jsonify({"error": "invalid pagination"}), 400

    total = g.db.execute(
        select(func.count()).select_from(models.Paper)
    ).scalar_one()

    papers = g.db.execute(
        select(models.Paper).order_by(models.Paper.id.asc()).limit(limit)
    ).scalars().all()
    paper_id_set: set[int] = {p.id for p in papers}

    journal_ids = [pid for pid in {p.journal_id for p in papers} if pid is not None]
    journal_tier: dict[int, int | None] = {}
    # SQLite 单语句最多 999 参数；超过时拆批查询避免崩溃。
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

    # Edge 全表扫一次然后 Python 过滤——比把 paper_id_set 塞进 in_ 安全
    # （n=2000 时双 in_ 会超 SQLite 999 参数上限）。
    edges_iter = g.db.execute(select(models.Edge)).scalars()
    edges_out: list[dict] = []
    for e in edges_iter:
        if e.from_paper_id in paper_id_set and e.to_paper_id in paper_id_set:
            edges_out.append({"id": e.id, "from": e.from_paper_id, "to": e.to_paper_id})

    return jsonify({
        "nodes": [
            {
                "id": p.id,
                "stem": p.stem,
                "title": p.title,
                "year": p.year,
                "status": p.status,
                "source": p.source,
                "quality_tier": (
                    journal_tier.get(p.journal_id)
                    if p.journal_id is not None else None
                ),
            }
            for p in papers
        ],
        "edges": edges_out,
        "total": total,
        "truncated": total > len(papers),
    })


# ─── M4.3 失败诊断面板 ───────────────────────────────────────────────

import os as _os
from pathlib import Path as _Path

# 项目根目录（app/routes/api.py → app/routes/ → app/ → 项目根）
_BASE_DIR = _Path(__file__).parent.parent.parent.resolve()


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
