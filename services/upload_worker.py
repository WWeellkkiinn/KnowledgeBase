"""UploadWorker —— 后台消费 TaskQueue 中 type="upload_pipeline" 的任务。

任务管线（task.payload_json 字段）：
  paper_id (int)  必填，已在上传 endpoint 创建好 status="uploading" 的 Paper 行

阶段：
  1) pdf2md     Pdf2MdService（默认 mineru-cloud）→ md_path
  2) title      从 md 首个 H1 抽取（paper.title 为空时）
  3) doi        若 paper.doi 为 None，doi_resolver(title) 反查
  4) crossref   若 DOI 已知，补 year/authors（best-effort）
  5) journal    JournalService.attach_to_paper（best-effort）
  6) refs       subprocess scripts/extract_refs.py → refs.json
  7) done       paper.status="analyzed"

并发约束：单 worker 线程；fetch_next 在多 worker 下会撕裂，start_worker 会显式拒启
（多 worker 守卫 app/__init__.py 已存在）。
进度：services.progress_bus.get_bus().publish(task_id=str(task.id), ...)。

路径约束：paper.pdf_path / md_path / refs_path 一律以 ROOT-相对 POSIX 字符串落库；
本模块所有磁盘操作前都用 _abs_under_root() 拼绝对路径并校验未越权，避免：
  - worker 在不同 CWD 下找不到文件
  - 落库的相对路径被外部串改后写到 ROOT 之外
"""
from __future__ import annotations

import atexit
import hashlib
import logging
import os
import re
import subprocess
import sys
import threading
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from sqlalchemy import select

from database import SessionLocal, models
from services._paths import ROOT
from services.doi_resolver import resolve_doi
from services.journal_service import JournalService
from services.pdf2md_service import Pdf2MdService
from services.progress_bus import get_bus
from services.task_queue import TaskQueue

_log = logging.getLogger(__name__)
_EXTRACT_REFS = ROOT / "scripts" / "extract_refs.py"
_ROOT_RESOLVED = ROOT.resolve()
_PAPERS_DIR_RESOLVED = (_ROOT_RESOLVED / "papers").resolve()

# 空闲时 worker 用 Event.wait 等待，外部 enqueue 后可调 wake_worker() 立即唤醒。
# 默认 30s 兜底（即使没人唤醒也会定期扫一次）。
_IDLE_WAIT_SECONDS = 30.0

_shutdown = threading.Event()
_wakeup = threading.Event()
_worker_thread: Optional[threading.Thread] = None
_thread_lock = threading.Lock()
_atexit_registered = False

UPLOAD_TASK_TYPE = "upload_pipeline"
BACKWARD_TRACK_TYPE = "backward_track"
FORWARD_TRACK_TYPE = "forward_track"
GENERATE_QUERIES_TASK_TYPE = "generate_queries"
_HANDLED_TYPES = (UPLOAD_TASK_TYPE, BACKWARD_TRACK_TYPE, FORWARD_TRACK_TYPE, GENERATE_QUERIES_TASK_TYPE)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _crossref_ua() -> str:
    """Crossref 礼貌池 User-Agent：带可联系邮箱时享用更稳定的限速档。"""
    email = os.environ.get("UNPAYWALL_EMAIL", "").strip()
    return f"KnowledgeBase/1.0 (mailto:{email})" if email else "KnowledgeBase/1.0"


def _emit(task_id: int, step: str, msg: str, **extra) -> None:
    payload = {"step": step, "message": msg}
    payload.update(extra)
    try:
        get_bus().publish(str(task_id), "progress", payload)
    except Exception:
        _log.exception("progress bus publish failed")


def compute_sha1(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(chunk), b""):
            h.update(buf)
    return h.hexdigest()


# ─── 路径安全工具 ───────────────────────────────────────────────────────────


def _abs_under_root(rel_or_abs: str | Path) -> Path:
    """把相对路径拼到 ROOT，绝对路径直接 resolve；最终结果必须落在 papers/ 下。

    任何越权（含 .. 穿越、被改成绝对系统路径）→ ValueError。
    """
    p = Path(rel_or_abs)
    abs_p = (p if p.is_absolute() else (_ROOT_RESOLVED / p)).resolve()
    try:
        abs_p.relative_to(_PAPERS_DIR_RESOLVED)
    except ValueError as e:
        raise ValueError(f"path escapes papers/: {rel_or_abs}") from e
    return abs_p


def _rel_to_root(p: Path) -> str:
    """把绝对路径规范成 ROOT-相对 POSIX 字符串；落 ROOT 之外则 ValueError。"""
    resolved = p.resolve()
    rel = resolved.relative_to(_ROOT_RESOLVED)
    return rel.as_posix()


# ─── 元数据辅助 ─────────────────────────────────────────────────────────────


def _extract_title_from_md(md_path: Path) -> Optional[str]:
    try:
        with open(md_path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^#\s+(.+)$", line.strip())
                if m:
                    candidate = m.group(1).strip()
                    if candidate and len(candidate) > 4:
                        return candidate
    except OSError:
        return None
    return None


# DOI 字符集（IETF 推荐）：路径段允许字母数字 + 一些标点；其他全部 URL-encode。
_DOI_ALLOWED_RE = re.compile(r"^10\.[0-9]{1,9}/[A-Za-z0-9._;()/:\-]+$")


def _crossref_metadata(doi: str, timeout: float = 10.0) -> dict:
    """best-effort 从 Crossref 拉 year/authors/title/abstract。失败返回 {}。

    DOI 走 urllib.parse.quote 编码，杜绝 `?#/../` 等改写 URL 路径的注入向量。
    """
    if not doi or not _DOI_ALLOWED_RE.match(doi):
        return {}
    encoded = urllib.parse.quote(doi, safe="")
    try:
        r = httpx.get(
            f"https://api.crossref.org/works/{encoded}",
            timeout=timeout,
            headers={"User-Agent": _crossref_ua()},
        )
        r.raise_for_status()
        msg = r.json().get("message") or {}
    except Exception as e:
        _log.info("crossref fetch failed for %s: %s", doi, e)
        return {}
    out: dict = {}
    issued = msg.get("issued") or {}
    parts = (issued.get("date-parts") or [[None]])[0]
    if parts and parts[0]:
        try:
            out["year"] = int(parts[0])
        except (TypeError, ValueError):
            pass
    authors_raw = msg.get("author") or []
    authors = []
    for a in authors_raw[:50]:
        family = a.get("family") or ""
        given = a.get("given") or ""
        full = (f"{given} {family}").strip()
        if full:
            authors.append(full)
    if authors:
        out["authors_json"] = authors
    if msg.get("title"):
        out["title"] = msg["title"][0] if isinstance(msg["title"], list) else str(msg["title"])
    if msg.get("abstract"):
        # Crossref abstract 可能含 JATS XML 标签。简单 strip 不够稳健：残缺标签或
        # &lt;script ...&gt; 文本会留下。这里用三步走：先剥所有 `<...>` 块，再 unescape
        # 实体（&amp;lt; 解开后可能含 <），再做第二轮 strip 保险。
        # 注意：前端务必用 `{{ }}` 文本插值渲染 abstract，禁止 v-html。
        import html as _html
        raw = str(msg["abstract"])
        cleaned = re.sub(r"<[^>]*>", " ", raw)
        cleaned = _html.unescape(cleaned)
        cleaned = re.sub(r"<[^>]*>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        out["abstract"] = cleaned[:8000]  # 上限保护，防异常巨长
    return out


def _run_extract_refs(md_path: Path, out_path: Path, timeout: float = 60.0) -> Optional[str]:
    try:
        proc = subprocess.run(
            [sys.executable, str(_EXTRACT_REFS), str(md_path)],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"extract_refs timeout >{timeout}s"
    if proc.returncode != 0:
        return proc.stderr.strip()[:500] or f"exit {proc.returncode}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(proc.stdout, encoding="utf-8")
    return None


# ─── 主管线 ─────────────────────────────────────────────────────────────────


class _UnknownTaskTypeError(RuntimeError):
    """未知 task type 是脏数据；不该重试。"""


def _process_one(session, task: models.Task) -> None:
    """根据 task.type 分发到具体处理函数。异常向上抛由 worker 主循环 _fail_task 处理。"""
    if task.type == UPLOAD_TASK_TYPE:
        _process_upload(session, task)
    elif task.type == BACKWARD_TRACK_TYPE:
        _process_track(session, task, direction="backward")
    elif task.type == FORWARD_TRACK_TYPE:
        _process_track(session, task, direction="forward")
    elif task.type == GENERATE_QUERIES_TASK_TYPE:
        _process_generate_queries(session, task)
    else:
        raise _UnknownTaskTypeError(f"unknown task type: {task.type}")


def _process_generate_queries(session, task: models.Task) -> None:
    """后台调 LLM 生成 OpenAlex 检索式。payload: {subscription_id: int}。

    异常向上抛由 worker 主循环 _fail_task 处理（attempt 自增 + 重试，达上限标 failed）。
    最终失败时 generated_queries 保持 None，前端列表行可显示"生成失败"。
    """
    payload = task.payload_json or {}
    sub_id = payload.get("subscription_id")
    if not sub_id:
        raise RuntimeError("generate_queries task missing subscription_id")
    sub = session.get(models.Subscription, int(sub_id))
    if sub is None:
        raise RuntimeError(f"subscription {sub_id} disappeared")
    if not sub.description:
        raise RuntimeError(f"subscription {sub_id} has no description")

    from services.llm_query_gen import generate_openalex_queries
    queries = generate_openalex_queries(sub.description)
    sub.generated_queries = queries or None
    session.commit()


def _process_track(session, task: models.Task, *, direction: str) -> None:
    """执行 backward/forward track。payload: paper_id, refresh(=False), limit(=None)。

    返回时 cache 已落库（_BaseTrackService.track 内部写入）；
    worker 不需要把列表数据 emit 回前端 —— 前端收到 done 事件后重新 GET 走 cache 命中。
    """
    payload = task.payload_json or {}
    raw_id = payload.get("paper_id") or task.paper_id
    try:
        paper_id = int(raw_id) if raw_id is not None else None
    except (TypeError, ValueError):
        raise RuntimeError(f"track task invalid paper_id: {raw_id!r}")
    if not paper_id:
        raise RuntimeError("track task missing paper_id")
    paper = session.get(models.Paper, paper_id)
    if paper is None:
        raise RuntimeError(f"paper {paper_id} disappeared")
    if not paper.doi:
        raise RuntimeError(f"paper {paper_id} has no DOI")

    refresh = bool(payload.get("refresh"))
    limit = payload.get("limit")
    label = "被引用" if direction == "forward" else "引用"
    _emit(task.id, "start", f"开始查询 {label}（{paper.stem}）", paper_id=paper.id, direction=direction)

    if direction == "forward":
        from services.forward_track_service import ForwardTrackService
        svc = ForwardTrackService(session)
        count_key = "citing_count"
    else:
        from services.backward_track_service import BackwardTrackService
        svc = BackwardTrackService(session)
        count_key = "references_count"

    # session 由 svc.track 内部管理事务（owns_session=False，因为传入了）
    result = svc.track(paper.doi, refresh=refresh, limit=limit, from_paper_id=paper.id)
    session.commit()
    _emit(
        task.id, "done",
        f"{label}已就绪：{result.get(count_key, 0)} 条",
        paper_id=paper.id, direction=direction,
        count=result.get(count_key, 0),
    )


def _process_upload(session, task: models.Task) -> None:
    """执行上传管线（原 _process_one 内容）。异常向上抛由 worker 主循环处理。

    事务边界（C4 修复，2 段）：
      段 A — 极短，提交 status='processing'（仅给 UI 观察性，无业务字段）
      段 B — 整条管线 step1..step6 为单事务：
          * 中间步骤只 session.flush()，绝不 commit
          * 末端成功 → 一次 commit（含 status='analyzed'）
          * 任意 step 抛错 → session.rollback() 整片回滚，避免脏字段残留
            （例如 md_path 落库但 references 失败导致 status 卡在 processing）

    设计取舍：不把 status='processing' 也并入大事务，是因为 pdf2md 可能跑数分钟，
    若不提前 commit，UI 会一直看不到状态变化。但 status='processing' 是无害的中间
    标记，独立短事务 commit 不会留下业务字段脏数据。
    """
    payload = task.payload_json or {}
    raw_id = payload.get("paper_id") or task.paper_id
    try:
        paper_id = int(raw_id) if raw_id is not None else None
    except (TypeError, ValueError):
        raise RuntimeError(f"upload task invalid paper_id: {raw_id!r}")
    if not paper_id:
        raise RuntimeError("upload task missing paper_id")
    paper = session.get(models.Paper, paper_id)
    if paper is None:
        raise RuntimeError(f"paper {paper_id} disappeared")

    _emit(task.id, "start", f"开始处理 {paper.stem}", paper_id=paper.id)

    # ── 段 A：observability commit ────────────────────────────────────────
    paper.status = "processing"
    session.commit()

    # ── 段 B：单事务管线（所有步骤共享一个事务，失败整片回滚）─────────────
    try:
        # 路径：落库为 ROOT-相对，先校验后用绝对路径
        if not paper.pdf_path:
            raise RuntimeError("paper.pdf_path empty")
        pdf_path = _abs_under_root(paper.pdf_path)
        if not pdf_path.exists():
            raise RuntimeError(f"PDF missing on disk: {paper.pdf_path}")

        # 1) PDF → MD
        _emit(task.id, "pdf2md", "PDF 解析中…")

        def _cb(step: str, msg: str) -> None:
            _emit(task.id, step, msg)

        output_dir = pdf_path.parent  # papers/<stem>/
        result = Pdf2MdService().convert(
            pdf_path, output_dir=output_dir, on_progress=_cb, stop_event=_shutdown,
        )
        if "error" in result:
            raise RuntimeError(f"pdf2md failed: {result['error']}")
        md_path = _abs_under_root(result["md_path"])
        paper.md_path = _rel_to_root(md_path)
        session.flush()

        # 2) Title
        if not paper.title:
            title = _extract_title_from_md(md_path)
            if title:
                paper.title = title
                session.flush()
                _emit(task.id, "title", f"标题：{title[:60]}")

        # 3) DOI 反查（duplicate → 立刻清理本上传，留既有 paper）
        if not paper.doi and paper.title:
            _emit(task.id, "doi", "查询 DOI…")
            try:
                doi = resolve_doi(paper.title)
            except Exception as e:
                _log.info("doi resolve failed: %s", e)
                doi = None
            if doi:
                existing = session.execute(
                    select(models.Paper).where(
                        models.Paper.doi == doi, models.Paper.id != paper.id
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    # 同一篇但 sha1 不同（如重排版 / 不同来源 PDF）：放弃本上传，统一归到既有 paper。
                    # 清理刚落盘的 pdf 目录避免孤儿；失败让 mark_failed 走，paper.status="failed"
                    _emit(
                        task.id, "doi",
                        f"DOI {doi} 已存在于 paper #{existing.id}，本上传视为重复",
                        duplicate_of=existing.id,
                    )
                    _cleanup_paper_files(paper)
                    # 把本 Paper 标 failed + failure_reason，调用方负责 mark_failed
                    raise _DuplicatePaperError(existing.id, doi)
                paper.doi = doi
                session.flush()
                _emit(task.id, "doi", f"DOI: {doi}")

        # 4) Crossref
        if paper.doi:
            _emit(task.id, "crossref", "拉取 Crossref 元数据…")
            meta = _crossref_metadata(paper.doi)
            if meta:
                if not paper.year and meta.get("year"):
                    paper.year = meta["year"]
                if not paper.authors_json and meta.get("authors_json"):
                    paper.authors_json = meta["authors_json"]
                if not paper.abstract and meta.get("abstract"):
                    paper.abstract = meta["abstract"]
                if not paper.title and meta.get("title"):
                    paper.title = meta["title"]
                session.flush()

        # 5) Journal
        if paper.doi:
            sp = session.begin_nested()
            try:
                JournalService().attach_to_paper(session, paper)
                session.flush()
                sp.commit()
            except Exception as e:
                sp.rollback()
                _log.info("journal attach failed: %s", e)

        # 6) References
        _emit(task.id, "refs", "抽取引用…")
        refs_path = output_dir / "refs.json"
        err = _run_extract_refs(md_path, refs_path)
        if err:
            _emit(task.id, "refs", f"引用抽取失败：{err}")
        else:
            try:
                paper.refs_path = _rel_to_root(refs_path)
                session.flush()
            except ValueError:
                pass  # 极端情况：refs 写到 ROOT 外，不入库但不影响 analyzed 状态

        paper.status = "analyzed"
        paper.analyzed_at = _utcnow()
        # 段 B 唯一 commit：step1..step6 全部成功才真正落库
        session.commit()
    except Exception:
        # 任意 step 失败 → 整片段 B 回滚，避免 md_path/title/doi 等脏字段残留
        # （注意：磁盘文件不在事务内，已写入的 md/refs 文件由失败处理或下次重跑覆盖）
        try:
            session.rollback()
        except Exception:
            _log.exception("rollback inside _process_upload failed")
        raise

    _emit(task.id, "done", "完成", paper_id=paper.id)


class _DuplicatePaperError(RuntimeError):
    def __init__(self, existing_id: int, doi: str) -> None:
        super().__init__(f"duplicate of paper #{existing_id} (doi={doi})")
        self.existing_id = existing_id
        self.doi = doi


def _cleanup_paper_files(paper: models.Paper) -> None:
    """删除某 Paper 的 pdf 所在目录（仅限 papers/<stem>/ 下；越权直接跳过）。"""
    if not paper.pdf_path:
        return
    try:
        pdf_abs = _abs_under_root(paper.pdf_path)
    except ValueError:
        return
    paper_dir = pdf_abs.parent
    try:
        paper_dir.relative_to(_PAPERS_DIR_RESOLVED)
    except ValueError:
        return
    if paper_dir == _PAPERS_DIR_RESOLVED:
        return  # 不允许误删 papers 根
    # rmtree 等价（避免引入 shutil 在锁路径下的复杂依赖）
    import shutil
    try:
        shutil.rmtree(paper_dir, ignore_errors=True)
    except Exception:
        _log.exception("cleanup paper dir failed: %s", paper_dir)


# ─── 失败处理 ───────────────────────────────────────────────────────────────


def _fail_task(
    session,
    task_id: int,
    paper_id: Optional[int],
    err_msg: str,
    *,
    force_terminal: bool = False,
) -> None:
    """原子化失败收尾：mark_failed → 若任务最终失败（attempt 耗尽）才把 paper.status=failed。

    设计意图：mark_failed 在 attempt < max_attempts 时会把 task 回 queued 排重试，
    此时若立即把 paper.status 改为 'failed'，UI 会在重试期间错误地显示失败。

    force_terminal=True：把 attempt 直接拉到 max_attempts 触发终态（用于
    _DuplicatePaperError 这种重试无意义的错误）。
    """
    try:
        session.rollback()
    except Exception:
        _log.exception("rollback before fail bookkeeping failed")

    if force_terminal:
        # 把 attempt 顶到 max_attempts，mark_failed 内的 `attempt < max_attempts` 判否
        t = session.get(models.Task, task_id)
        if t is not None:
            t.attempt = max(t.attempt, t.max_attempts)
            session.flush()

    tq = TaskQueue(session)
    tq.mark_failed(task_id, err_msg[:1000])
    session.flush()

    task_obj = session.get(models.Task, task_id)
    is_terminal = task_obj is not None and task_obj.status == "failed"
    task_type = task_obj.type if task_obj is not None else ""

    # 只有上传管线失败才把 paper.status 改 failed；track 失败仅记任务错误，paper 本身仍 OK
    if paper_id and is_terminal and task_type == UPLOAD_TASK_TYPE:
        p = session.get(models.Paper, paper_id)
        if p is not None:
            p.status = "failed"
            p.failure_reason = err_msg[:1000]
            session.flush()
    session.commit()
    _emit(task_id, "failed" if is_terminal else "retry", err_msg[:500])


# ─── Worker 主循环 ──────────────────────────────────────────────────────────


def wake_worker() -> None:
    """外部 enqueue 后调用，立刻唤醒 idle 中的 worker。"""
    _wakeup.set()


def _worker_loop() -> None:
    _log.info("upload-worker thread started")
    while not _shutdown.is_set():
        session = SessionLocal()
        task_id: Optional[int] = None
        paper_id: Optional[int] = None
        try:
            tq = TaskQueue(session)
            # C3 lost-wakeup 修复：必须在 fetch_next 之前 clear()。
            # 顺序：clear → fetch → (None) → wait
            #   - 若生产者在 clear 之前 set：本次 fetch 必然能拿到任务，进入处理分支
            #   - 若生产者在 clear 之后、wait 之前 set：wait 立即返回
            #   - 若生产者在 wait 期间 set：wait 正常被唤醒
            # 旧顺序（fetch → clear → wait）有窗口：fetch 返回 None 后、clear 之前
            # 生产者 set + enqueue，会被 clear 抹掉 → 任务卡到 _IDLE_WAIT_SECONDS。
            _wakeup.clear()
            # 单次 type IN (...) 查询，全局 FIFO（按 id 升序），避免顺序循环带来的
            # 公平问题（upload 永远优先 → backward/forward 饿死）+ 3 倍 DB roundtrip
            task = tq.fetch_next(types=list(_HANDLED_TYPES))
            session.commit()
            if task is None:
                session.close()
                # _wakeup 是统一信号：wake_worker() set 唤醒；stop_worker() 同时 set
                # _shutdown 与 _wakeup 让等待立刻返回。返回后检查 _shutdown 决定退出。
                _wakeup.wait(_IDLE_WAIT_SECONDS)
                if _shutdown.is_set():
                    break
                continue
            task_id = task.id
            paper_id = (task.payload_json or {}).get("paper_id") or task.paper_id
            try:
                _process_one(session, task)
                tq.mark_done(task.id)
                session.commit()
            except Exception as e:
                _log.exception("upload task %s failed", task.id)
                err_msg = str(e) or e.__class__.__name__
                # 这些异常重试也修复不了，直接终态失败
                force_terminal = isinstance(e, (_DuplicatePaperError, _UnknownTaskTypeError))
                # 主 session 先关，避免与 fail_session 在 SQLite 上锁竞争
                try:
                    session.close()
                except Exception:
                    pass
                fail_session = SessionLocal()
                try:
                    _fail_task(
                        fail_session, task_id, paper_id, err_msg,
                        force_terminal=force_terminal,
                    )
                finally:
                    fail_session.close()
                # 跳过外层 finally 的 session.close（已关）
                session = None  # type: ignore[assignment]
        except Exception:
            _log.exception("upload worker loop iteration failed")
            try:
                session.rollback()
            except Exception:
                pass
            if task_id is not None:
                # 兜底：worker 主循环异常时也要把 task 推进，否则 stuck running
                fs = SessionLocal()
                try:
                    _fail_task(fs, task_id, paper_id, "worker loop crashed")
                except Exception:
                    _log.exception("fallback _fail_task also failed")
                finally:
                    fs.close()
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass
    _log.info("upload-worker thread exiting")


def start_worker() -> None:
    """启动 worker 线程（幂等）。app 启动时调用一次。

    多 worker 检测：fetch_next 无原子领取，进程内只能有 1 个 worker 线程。
    多 Flask 进程（gunicorn -w N）下不应启动 → 调用方应在多 worker 守卫之后再调。
    """
    global _worker_thread, _atexit_registered
    with _thread_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        # 复位崩溃残留
        session = SessionLocal()
        try:
            n = TaskQueue(session).reset_stale()
            session.commit()
            if n:
                _log.info("upload-worker reset %d stale tasks", n)
        except Exception:
            _log.exception("upload-worker reset_stale failed")
            session.rollback()
        finally:
            session.close()
        _shutdown.clear()
        _wakeup.clear()
        t = threading.Thread(target=_worker_loop, daemon=True, name="upload-worker")
        t.start()
        _worker_thread = t
        if not _atexit_registered:
            atexit.register(stop_worker)
            _atexit_registered = True


def stop_worker(timeout: float = 10.0) -> None:
    """关闭 worker。daemon 线程在进程退出时被硬杀，故主动 set 后等待最长 timeout。

    timeout 内未结束的长操作（HTTP 轮询、subprocess）将被强制中断；
    下次启动会通过 reset_stale 把 running 任务复位重跑。
    """
    _shutdown.set()
    _wakeup.set()
    with _thread_lock:
        t = _worker_thread
    if t is not None:
        t.join(timeout=timeout)


__all__ = [
    "start_worker",
    "stop_worker",
    "wake_worker",
    "compute_sha1",
    "UPLOAD_TASK_TYPE",
    "GENERATE_QUERIES_TASK_TYPE",
]
