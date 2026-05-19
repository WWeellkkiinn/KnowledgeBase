"""REST API blueprint（M1.5 最小只读集）。"""
from __future__ import annotations

import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path, Path as _Path
from typing import Optional

from flask import Blueprint, Response, abort, g, jsonify, request, stream_with_context
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app import limiter
from database import models


_log = logging.getLogger(__name__)

bp = Blueprint("api", __name__)
# 全局 Bearer 鉴权统一在 app/__init__.py 的 _require_bearer_token 处理；
# 此蓝图不再单独鉴权。

# 异步 digest 全局互斥锁，防止 /digest/send?async=1 被重放堆积线程
_digest_lock = threading.Lock()


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
    # 过滤条件抽出，count 与 list 共用同一 where 列表（避免 SELECT 全列再外层 count
    # 的 subquery 退化 —— DB 可直接走索引）
    filters = []
    if tier == "core":
        filters.append(models.Paper.is_core.is_(True))
    elif tier == "stub":
        filters.append(models.Paper.is_core.is_(False))
    if status:
        filters.append(models.Paper.status == status)
    if source:
        filters.append(models.Paper.source == source)

    # total
    count_stmt = select(func.count(models.Paper.id))
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = g.db.execute(count_stmt).scalar_one()

    # 列表
    list_stmt = (
        select(models.Paper)
        .options(joinedload(models.Paper.journal))
        .order_by(models.Paper.id.asc())
        .limit(limit)
        .offset(offset)
    )
    if filters:
        list_stmt = list_stmt.where(*filters)
    rows = g.db.execute(list_stmt).scalars().all()
    return jsonify({
        "items": [_paper_to_dict(p, include_journal=True) for p in rows],
        "limit": limit,
        "offset": offset,
        "total": int(total),
    })


_UPLOAD_MAX_BYTES = 50 * 1024 * 1024  # 50MB
_UPLOAD_CHUNK = 1 * 1024 * 1024
_STEM_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")
_PAPERS_DIR = (_BASE_DIR / "papers").resolve()


def _safe_stem(name: str) -> str:
    base = (name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if base.lower().endswith(".pdf"):
        base = base[:-4]
    cleaned = _STEM_SAFE_RE.sub("_", base).strip("._-")[:120]
    return cleaned or "upload"


@bp.post("/papers/upload")
@limiter.limit("5 per minute")
def upload_paper():
    """上传 PDF 入库。multipart/form-data 字段 file。

    设计要点：
      - 端点级 Content-Length 早拒绝（不依赖全局 MAX_CONTENT_LENGTH）
      - 流式 chunked 读：增量 sha1 + 写临时文件，杜绝 50MB 整文件常驻内存
      - PDF 魔数校验（首 chunk 头 8 字节）
      - stem = "<base>_<sha1[:8]>"：永远附加 sha1 前缀，消除并发命名竞争
      - 严格顺序：sha1 dedup → flush+enqueue → rename tmp→target → commit
        中途异常 finally 清理 tmp 文件、rollback；DB 与磁盘不会半新半旧
      - 入队后 wake_worker()，worker 立即拾取，无 idle 等待
    """
    import hashlib as _hashlib
    import tempfile as _tempfile

    # 端点级 Content-Length 早拒绝（不依赖全局 MAX_CONTENT_LENGTH）
    cl = request.content_length
    if cl is not None and cl > _UPLOAD_MAX_BYTES + 4096:  # 4KB 给 multipart 头留缓冲
        return jsonify({"error": f"file too large; limit {_UPLOAD_MAX_BYTES} bytes"}), 413

    if "file" not in request.files:
        return jsonify({"error": "missing file field"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "empty filename"}), 400

    # 流式读：chunk 增量做 sha1 + 写入临时文件；超限即拒，避免整文件常驻内存
    sha1_hasher = _hashlib.sha1()
    size = 0
    first_chunk: bytes = b""
    # 临时文件落 papers/.tmp/；与最终目录同卷，rename 才是原子的
    tmp_dir = _PAPERS_DIR / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = _tempfile.mkstemp(prefix="upload_", suffix=".pdf", dir=str(tmp_dir))
    tmp_path: Optional[Path] = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "wb") as out:
            stream = f.stream
            while True:
                chunk = stream.read(_UPLOAD_CHUNK)
                if not chunk:
                    break
                if not first_chunk:
                    first_chunk = chunk[:8]
                size += len(chunk)
                if size > _UPLOAD_MAX_BYTES:
                    return jsonify({"error": f"file too large; limit {_UPLOAD_MAX_BYTES} bytes"}), 413
                sha1_hasher.update(chunk)
                out.write(chunk)
        if size == 0:
            return jsonify({"error": "empty file"}), 400
        if not first_chunk.startswith(b"%PDF-"):
            return jsonify({"error": "not a PDF (magic bytes mismatch)"}), 400

        sha1 = sha1_hasher.hexdigest()

        # sha1 去重
        existing = g.db.execute(
            select(models.Paper).where(models.Paper.sha1 == sha1)
        ).scalar_one_or_none()
        if existing is not None:
            return jsonify({
                "paper_id": existing.id,
                "task_id": None,
                "deduped": True,
                "reason": "same sha1",
            }), 200

        # stem：永远附加 sha1 短前缀，消除并发命名竞争（不同 sha1 永远不撞 stem）
        base_stem = _safe_stem(f.filename)
        stem = f"{base_stem}_{sha1[:8]}"
        # 极端兜底：若 stem 仍占用（不同上传文件碰撞前 8 位 sha1），用更长前缀
        if g.db.execute(
            select(models.Paper.id).where(models.Paper.stem == stem)
        ).scalar_one_or_none() is not None:
            stem = f"{base_stem}_{sha1[:16]}"

        # 先校验目标路径合法，再 mkdir + rename；杜绝 traversal 副作用
        target_dir = (_PAPERS_DIR / stem).resolve()
        try:
            target_dir.relative_to(_PAPERS_DIR)
        except ValueError:
            return jsonify({"error": "path traversal blocked"}), 400
        target_pdf = target_dir / f"{stem}.pdf"
        try:
            target_pdf.resolve().relative_to(_PAPERS_DIR)
        except ValueError:
            return jsonify({"error": "path traversal blocked"}), 400

        # 写盘 + DB 入队顺序：先 commit DB，再 rename 临时文件入 papers/<stem>/
        # —— 一旦中途异常，DB 与磁盘要么都没改，要么都改成；杜绝孤儿文件。
        paper = models.Paper(
            stem=stem,
            title=None,
            sha1=sha1,
            pdf_path=f"papers/{stem}/{stem}.pdf",
            status="uploading",
            source="upload",
            is_core=True,
        )
        g.db.add(paper)
        g.db.flush()

        from services.task_queue import TaskQueue
        from services.upload_worker import UPLOAD_TASK_TYPE, wake_worker

        tq = TaskQueue(g.db)
        task = tq.enqueue(
            type=UPLOAD_TASK_TYPE,
            paper_id=paper.id,
            payload={"paper_id": paper.id, "stem": stem, "sha1": sha1},
            max_attempts=2,
        )

        # 入队成功（DB flush）后才落盘到最终位置
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(str(tmp_path), str(target_pdf))
        except OSError as e:
            # rename 失败：回滚事务 → 文件 + DB 同时不变
            g.db.rollback()
            return jsonify({"error": f"file move failed: {e}"}), 500
        tmp_path = None  # 标记已迁移，finally 跳过 unlink

        # commit 失败时已落盘的 target_pdf 是孤儿（DB 已 rollback 但磁盘有文件），需删
        try:
            g.db.commit()
        except Exception:
            g.db.rollback()
            try:
                if target_pdf.exists():
                    target_pdf.unlink()
                # 若 target_dir 为空目录，一并删
                try:
                    target_dir.rmdir()
                except OSError:
                    pass
            except OSError:
                _log.exception("post-rollback cleanup failed: %s", target_pdf)
            raise
        wake_worker()
    finally:
        # 若中途未成功 commit / 未 rename，残留 tmp 文件必须删
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                _log.exception("cleanup tmp upload failed: %s", tmp_path)

    return jsonify({
        "paper_id": paper.id,
        "task_id": task.id,
        "deduped": False,
        "stem": stem,
    }), 201


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


_TRACK_DEFAULT_LIMIT = 100
_TRACK_MAX_LIMIT = 500
# 全局并发 track 任务上限：防止用户连续点不同 paper 把 SS/OA 配额吃完
# （queued + running 总和；超过后新请求返回 503 让用户等等）
_TRACK_MAX_INFLIGHT = 20
# 串行化 enqueue：把"查 pending + enqueue"放进同一进程锁，杜绝并发重复入队
_track_enqueue_lock = threading.Lock()


def _paginate_track_result(result: dict, papers_key: str, offset: int, limit: int) -> dict:
    """对 cache 中完整结果列表做分页切片。

    实现要点：
      - 直接读取原列表的引用 + 切片，避免 list(...) 全量拷贝（6MB 数据下浪费 CPU）
      - 切片本身是浅拷贝（Python list slicing），新 dict 顶层也浅拷贝
      - 不要 mutate 原 result（cache 行）；调用方传入的 result 已经是 dict()  shallow copy
    """
    full = result.get(papers_key) or []
    total_len = len(full)
    sliced = full[offset: offset + limit]
    paginated = dict(result)
    paginated[papers_key] = sliced
    paginated["offset"] = offset
    paginated["limit"] = limit
    paginated["has_more"] = (offset + len(sliced)) < total_len
    return paginated


def _parse_track_body() -> tuple[bool, int, int, Optional[int]]:
    """解析 track endpoint 的 body：refresh / offset / limit / fetch_limit。

    fetch_limit = body['limit'] 时仅作 worker 拉取阶段的总上限（默认 None=拉全量），
    页面分页用的 limit = body['page_limit'] 默认 100。

    返回 (refresh, page_limit, offset, fetch_limit)；非法值抛 ValueError。
    """
    body = request.get_json(silent=True) or {}
    refresh = bool(body.get("refresh", False))

    raw_page_limit = body.get("page_limit", _TRACK_DEFAULT_LIMIT)
    try:
        page_limit = max(1, min(int(raw_page_limit), _TRACK_MAX_LIMIT))
    except (TypeError, ValueError):
        raise ValueError("invalid page_limit")

    raw_offset = body.get("offset", 0)
    try:
        offset = max(0, int(raw_offset))
    except (TypeError, ValueError):
        raise ValueError("invalid offset")

    raw_limit = body.get("limit")
    if raw_limit is None:
        fetch_limit = None
    else:
        try:
            fetch_limit = max(1, int(raw_limit))
        except (TypeError, ValueError):
            raise ValueError("invalid limit")

    return refresh, page_limit, offset, fetch_limit


def _track_endpoint(paper_id: int, direction: str):
    """通用 track endpoint。direction: 'forward' | 'backward'。

    设计：
      - cache 命中 + !refresh → 200 + 分页切片（毫秒）
      - cache miss / refresh → enqueue task，返回 202 + {task_id, status: 'queued'}
        前端订阅 socket.io /progress/{task_id}，收到 done 事件后重发本 endpoint
        即可命中刚写入的 cache。
    """
    if request.content_length is not None and request.content_length > 1024:
        return jsonify({"error": "request body too large"}), 413

    p = g.db.get(models.Paper, paper_id)
    if p is None:
        return jsonify({"error": "not found"}), 404
    if not p.doi:
        return jsonify({"error": "paper has no DOI"}), 422

    try:
        refresh, page_limit, offset, fetch_limit = _parse_track_body()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if direction == "forward":
        from services.forward_track_service import ForwardTrackService
        svc = ForwardTrackService(db_session=g.db)
        papers_key = "citing_papers"
        task_type = "forward_track"
    else:
        from services.backward_track_service import BackwardTrackService
        svc = BackwardTrackService(db_session=g.db)
        papers_key = "referenced_papers"
        task_type = "backward_track"

    # 快路径：cache 命中且未强制刷新
    if not refresh:
        from services.reference_fetcher import normalize_doi
        doi_norm = normalize_doi(p.doi)
        if doi_norm:
            cached = svc._read_cache(g.db, doi_norm)
            if cached is not None:
                payload = dict(cached.result_json)
                payload["cached"] = True
                return jsonify(_paginate_track_result(payload, papers_key, offset, page_limit))

    # 慢路径：把"查 pending + 检查并发上限 + enqueue"放进进程锁，
    # 避免两个并发请求同时通过 pending check 重复入队。
    from sqlalchemy import select as _select
    from services.task_queue import TaskQueue
    from services.upload_worker import (
        BACKWARD_TRACK_TYPE, FORWARD_TRACK_TYPE, wake_worker,
    )

    with _track_enqueue_lock:
        existing_task = g.db.execute(
            _select(models.Task).where(
                models.Task.type == task_type,
                models.Task.paper_id == paper_id,
                models.Task.status.in_(("queued", "running")),
            ).order_by(models.Task.id.desc()).limit(1)
        ).scalar_one_or_none()

        if existing_task is not None:
            # refresh=True 的请求落到已存在的非 refresh 任务上：升级 payload.refresh
            # 让 worker 真的去刷新（payload_json 是 MutableJSON，flush 即落库）
            if refresh:
                payload = dict(existing_task.payload_json or {})
                if not payload.get("refresh"):
                    payload["refresh"] = True
                    existing_task.payload_json = payload
                    g.db.flush()
                    g.db.commit()
            return jsonify({
                "task_id": existing_task.id,
                "status": existing_task.status,
                "message": f"{direction}-track 已在队列中"
                           + ("，已升级为强制刷新" if refresh else ""),
            }), 202

        # 全局并发 track 任务上限保护：超过即拒绝，让用户等队列消化
        inflight = g.db.execute(
            _select(func.count(models.Task.id)).where(
                models.Task.type.in_((FORWARD_TRACK_TYPE, BACKWARD_TRACK_TYPE)),
                models.Task.status.in_(("queued", "running")),
            )
        ).scalar_one()
        if int(inflight) >= _TRACK_MAX_INFLIGHT:
            return jsonify({
                "error": "track queue full",
                "inflight": int(inflight),
                "limit": _TRACK_MAX_INFLIGHT,
                "message": "后台 track 任务队列已满，请稍后再试",
            }), 503

        tq = TaskQueue(g.db)
        task = tq.enqueue(
            type=task_type,
            paper_id=paper_id,
            payload={"paper_id": paper_id, "refresh": refresh, "limit": fetch_limit},
            max_attempts=2,
        )
        g.db.commit()
    wake_worker()
    return jsonify({
        "task_id": task.id,
        "status": "queued",
        "message": f"{direction}-track 已入队，请稍候",
    }), 202


@bp.post("/papers/<int:paper_id>/forward-track")
@limiter.limit("10 per minute")
def forward_track(paper_id: int):
    """触发前向追踪。

    body 字段：
      - refresh (bool, default false)：强制刷新 cache
      - page_limit (int, default 100, max 500)：本次响应返回多少条
      - offset (int, default 0)：翻页起点
      - limit (int, optional)：worker 拉取阶段的总上限（不传则拉全量）

    返回：
      - 200 + 分页数据（cache 命中）
      - 202 + {task_id, status} （cache miss / refresh，已入队后台 worker）
      - 422 论文无 DOI
    """
    return _track_endpoint(paper_id, "forward")


@bp.post("/papers/<int:paper_id>/backward-track")
@limiter.limit("10 per minute")
def backward_track(paper_id: int):
    """触发后向追踪。body / 返回语义同 forward-track，但 papers_key=referenced_papers。"""
    return _track_endpoint(paper_id, "backward")


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
@limiter.limit("5 per minute")
def ai_analyze_paper(paper_id: int):
    """触发单篇论文的 AI 打标签 + 精炼（F1+F2）。
    幂等：已分析过的论文除非 body 传 refresh=true，否则直接返回现有结果，
    避免公网重放刷算力。"""
    p = g.db.get(models.Paper, paper_id)
    if p is None:
        return jsonify({"error": "not found"}), 404
    if not p.abstract:
        return jsonify({"error": "no abstract"}), 422
    refresh = bool((request.get_json(silent=True) or {}).get("refresh", False))
    # 幂等守卫：仅当上次分析"已完成"（ai_summary 非空 且 tags 字段被显式赋过值）时跳过。
    # tags 用 is not None 判断（不是 truthy）：历史成功分析但 LLM 没产出标签
    # 会落 tags=[]，仍属"完成"状态，再跑只会重复烧 LLM 成本。
    # 失败路径仅写 ai_analyzed_at，不写 ai_summary，会自然落到重试分支。
    if (
        p.ai_analyzed_at is not None
        and p.ai_summary
        and p.tags is not None
        and not refresh
    ):
        return jsonify(_paper_to_dict(p, include_journal=True))
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


# ─── 感兴趣领域 CRUD ────────────────────────────────────────────────


def _sub_to_dict(s: models.Subscription) -> dict:
    return {
        "id": s.id,
        "description": s.description or "",
        "active": bool(s.active),
        "generated_queries": s.generated_queries or [],
        "queries_pending": bool(s.description and not s.generated_queries),
        "last_filled_at": _iso_utc(s.last_filled_at),
        "query_refreshed_at": _iso_utc(s.query_refreshed_at),
    }


@bp.get("/subscriptions")
def list_subscriptions():
    from services import SubscriptionService
    active = request.args.get("active")
    only_active = active in ("1", "true", "yes")
    rows = SubscriptionService.list_all(g.db, active_only=only_active)
    return jsonify({"items": [_sub_to_dict(s) for s in rows]})


@bp.post("/subscriptions")
@limiter.limit("5 per minute")
def create_subscription():
    from services import SubscriptionService
    body = request.get_json(silent=True) or {}
    try:
        sub = SubscriptionService().create(
            g.db,
            description=body.get("description", ""),
            active=bool(body.get("active", True)),
        )
        g.db.commit()
    except ValueError as e:
        g.db.rollback()
        return jsonify({"error": str(e)}), 400
    try:
        from services.upload_worker import wake_worker
        wake_worker()
    except Exception:
        pass
    return jsonify(_sub_to_dict(sub)), 201


@bp.patch("/subscriptions/<int:sub_id>")
@limiter.limit("10 per minute")
def update_subscription(sub_id: int):
    from services import SubscriptionService
    body = request.get_json(silent=True) or {}
    try:
        sub, description_changed = SubscriptionService.update(
            g.db, sub_id,
            active=body.get("active"),
            description=body.get("description"),
        )
    except ValueError as e:
        g.db.rollback()
        return jsonify({"error": str(e)}), 400
    if sub is None:
        return jsonify({"error": "not found"}), 404
    g.db.commit()
    if description_changed:
        import threading as _t
        from database import SessionLocal as _SL
        from services.explore_service import _compute_pre_scores
        sid = sub.id
        def _bg_recompute(s_id):
            s = _SL()
            try:
                _compute_pre_scores(s, s_id)
            finally:
                s.close()
        _t.Thread(target=_bg_recompute, args=(sid,), daemon=True).start()
    try:
        from services.upload_worker import wake_worker
        wake_worker()
    except Exception:
        pass
    return jsonify(_sub_to_dict(sub))


@bp.delete("/subscriptions/<int:sub_id>")
def delete_subscription(sub_id: int):
    from services import SubscriptionService
    if not SubscriptionService.delete(g.db, sub_id):
        return jsonify({"error": "not found"}), 404
    g.db.commit()
    return "", 204


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
@limiter.limit("3 per hour")
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
@limiter.limit("2 per hour")
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
        # 全局互斥：未释放前重复请求直接 409，防止公网重放堆积 SMTP/DB 任务
        if not _digest_lock.acquire(blocking=False):
            return jsonify({"error": "digest already running"}), 409

        # 捕获真实 app 对象供后台线程建立 app_context（脱离请求上下文后
        # send_digest 内部若使用 current_app/g 不会 RuntimeError）
        from flask import current_app
        _app = current_app._get_current_object()

        def _bg():
            from database import SessionLocal
            try:
                with _app.app_context():
                    session = SessionLocal()
                    try:
                        send_digest(session, **kwargs)
                    except Exception:
                        # 后台异步语义：异常无法 1:1 同步报告给客户端，
                        # 只能写日志，避免静默吞错
                        _log.exception("async send_digest failed")
                    finally:
                        session.close()
            finally:
                _digest_lock.release()

        try:
            threading.Thread(target=_bg, name="digest-async", daemon=True).start()
        except Exception:
            # Thread 构造/启动失败：锁必须立即释放，否则永久 409
            _digest_lock.release()
            _log.exception("failed to start digest-async thread")
            return jsonify({"error": "failed to start background task"}), 500
        return jsonify({"accepted": True})

    try:
        return jsonify(send_digest(g.db, **kwargs))
    except Exception as exc:
        _log.exception("send_digest_now failed: %s", type(exc).__name__)
        return jsonify({"error": "digest failed"}), 502


# ── 探索池 ──────────────────────────────────────────────────────────────
@bp.get("/explore/cards")
def get_explore_cards():
    """获取探索池待评卡片列表，按 embedding 得分排序。"""
    from services.explore_service import get_explore_cards
    sub_id = request.args.get("sub_id", type=int)
    limit = request.args.get("limit", 10, type=int)
    exclude_raw = request.args.get("exclude", "")
    exclude_ids = [int(x) for x in exclude_raw.split(",") if x.strip().isdigit()]
    if not sub_id:
        return jsonify({"error": "sub_id required"}), 400
    cards = get_explore_cards(g.db, sub_id, limit=min(limit, 30), exclude_ids=exclude_ids)
    return jsonify({"items": cards, "count": len(cards)})


@bp.post("/explore/<int:pool_id>/action")
@limiter.limit("60 per minute")
def record_explore_action(pool_id: int):
    """记录用户对探索池卡片的操作：saved / skipped / passed。"""
    from services.explore_service import record_explore_action
    body = request.get_json(silent=True) or {}
    action = body.get("action", "")
    try:
        result = record_explore_action(g.db, pool_id, action)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/explore/<int:pool_id>/undo")
@limiter.limit("60 per minute")
def explore_undo(pool_id: int):
    from services.explore_service import undo_explore_action
    try:
        return jsonify(undo_explore_action(g.db, pool_id))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@bp.post("/explore/refill")
@limiter.limit("3 per minute")
def refill_explore_pool():
    """手动触发探索池补充。"""
    from services.explore_service import fill_explore_pool, score_and_embed_pending
    sub_id = request.args.get("sub_id", type=int)
    if not sub_id:
        return jsonify({"error": "sub_id required"}), 400
    sub = g.db.get(models.Subscription, sub_id)
    if not sub:
        return jsonify({"error": "subscription not found"}), 404

    # 只有已打分的可用卡片 ≥ 10 才拒绝（防刷 OpenAlex）
    scored_count = g.db.execute(
        select(func.count()).select_from(models.ExplorePool).where(
            models.ExplorePool.subscription_id == sub_id,
            models.ExplorePool.action.is_(None),
            models.ExplorePool.scored_at.isnot(None),
        )
    ).scalar() or 0
    if scored_count >= 100:
        return jsonify({"error": "pool has enough cards", "pending": scored_count}), 409

    # 有未打分的卡片时跳过 OpenAlex 拉取，直接打分
    unscored_count = g.db.execute(
        select(func.count()).select_from(models.ExplorePool).where(
            models.ExplorePool.subscription_id == sub_id,
            models.ExplorePool.action.is_(None),
            models.ExplorePool.scored_at.is_(None),
        )
    ).scalar() or 0

    fill_result = {"added": 0}
    if unscored_count < 100:
        fill_result = fill_explore_pool(g.db, sub)

    # 先同步打分第一批（10篇），让用户立刻看到卡片
    first_batch = score_and_embed_pending(g.db, sub_id, max_items=10)

    # 剩余卡片放后台线程继续处理
    import threading
    from database import SessionLocal as _SL

    def _bg(sid):
        s = _SL()
        try:
            score_and_embed_pending(s, sid)
        finally:
            s.close()

    threading.Thread(target=_bg, args=(sub_id,), daemon=True).start()
    return jsonify({**fill_result, **first_batch, "status": "first_batch_ready"})


