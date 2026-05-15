"""TaskQueue —— 基于 `tasks` 表的任务队列（M1.4）。

替代 `papers/_manifest.json` 作为状态真相源。支持：
- enqueue / fetch_next / mark_running / mark_done / mark_failed
- 启动时 reset_stale：扫 `running` → 重置为 `queued`（崩溃恢复）
- 自动重试：失败任务 attempt < max_attempts 时回排队

并发模型：单进程 worker（SocketIO threading 模式下多 HTTP worker 走同一进程）。
fetch_next 用 SELECT + UPDATE，多线程并发情况下可能两个 worker 同时领取同一行
（无 SELECT FOR UPDATE）；要在多进程/多 worker 下安全运行需扩展 lease：
- 加 `worker_id` 列
- fetch_next 改 atomic UPDATE...RETURNING 配 lease 时间戳

与 _manifest.json 共存：M1.4 期间双写（manifest 仍由 expand.py 维护），
未来 milestone 完成切换后移除 manifest 入口。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import case, literal, select, update
from sqlalchemy.orm import Session

from database import models

_ERROR_LOG_MAX_BYTES = 8 * 1024  # 8KB 上限，避免无界增长


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TaskQueue:
    """单进程任务队列。多 worker 并发时需扩展 SELECT FOR UPDATE / lease。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ─── 入队 ────────────────────────────────────────────────────────

    def enqueue(
        self,
        type: str,
        *,
        paper_id: Optional[int] = None,
        payload: Optional[dict] = None,
        parent_task_id: Optional[int] = None,
        max_attempts: int = 3,
    ) -> models.Task:
        task = models.Task(
            type=type,
            paper_id=paper_id,
            payload_json=payload,
            parent_task_id=parent_task_id,
            max_attempts=max_attempts,
        )
        self.session.add(task)
        self.session.flush()
        return task

    # ─── 出队 ────────────────────────────────────────────────────────

    def fetch_next(
        self,
        type: Optional[str] = None,
        types: Optional[list[str]] = None,
    ) -> Optional[models.Task]:
        """取一个待执行任务并标记 running。FIFO（按 id 升序）。

        type：精确匹配单一类型
        types：匹配集合中任意类型（与 type IN (...) 等价）；同时传则取 type 单值
        FIFO 全局公平：按 id 升序，所有 type 共享同一顺序，不会出现某 type 饥饿
        """
        stmt = (
            select(models.Task)
            .where(models.Task.status == "queued")
            .order_by(models.Task.id.asc())
            .limit(1)
        )
        if type:
            stmt = stmt.where(models.Task.type == type)
        elif types:
            stmt = stmt.where(models.Task.type.in_(tuple(types)))
        task = self.session.execute(stmt).scalar_one_or_none()
        if task is None:
            return None
        task.status = "running"
        task.attempt += 1
        task.started_at = _utcnow()
        self.session.flush()
        return task

    # ─── 状态转换 ────────────────────────────────────────────────────

    def mark_done(self, task_id: int) -> None:
        task = self.session.get(models.Task, task_id)
        if task is None:
            return
        task.status = "completed"
        task.finished_at = _utcnow()
        self.session.flush()

    def mark_failed(self, task_id: int, error: str) -> None:
        """失败：attempt < max_attempts 则回 queued，否则 failed。"""
        task = self.session.get(models.Task, task_id)
        if task is None:
            return
        combined = (task.error_log or "") + f"\n[attempt {task.attempt}] {error}"
        # 截断防无界增长，保留最新的尾部（重要错误信息更可能在末尾）
        if len(combined) > _ERROR_LOG_MAX_BYTES:
            combined = "...[truncated]...\n" + combined[-_ERROR_LOG_MAX_BYTES:]
        task.error_log = combined
        if task.attempt < task.max_attempts:
            task.status = "queued"
            task.started_at = None
            task.finished_at = None
        else:
            task.status = "failed"
            task.finished_at = _utcnow()
        self.session.flush()

    # ─── 崩溃恢复 ────────────────────────────────────────────────────

    def reset_stale(self) -> int:
        """把所有 status=running 的任务重置为 queued，并回滚 attempt 计数。

        语义：崩溃恢复时不应额外消耗重试预算。`fetch_next` 在领取时会再次自增
        `attempt`，所以这里必须先减 1（不小于 0），保持 max_attempts 的语义不变。
        """
        attempt_col = models.Task.attempt
        stmt = (
            update(models.Task)
            .where(models.Task.status == "running")
            .values(
                status="queued",
                started_at=None,
                attempt=case(
                    (attempt_col > 0, attempt_col - 1),
                    else_=literal(0),
                ),
            )
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount or 0

    # ─── 查询 ────────────────────────────────────────────────────────

    def count_by_status(self) -> dict[str, int]:
        """聚合任务计数，按 status 分组。

        注意：返回稀疏 dict —— 没有任务的 status 不会出现在 key 中，调用方应使用
        `counts.get("running", 0)` 而非直接索引。
        """
        from sqlalchemy import func as sa_func
        rows = self.session.execute(
            select(models.Task.status, sa_func.count(models.Task.id))
            .group_by(models.Task.status)
        ).all()
        return {status: int(count) for status, count in rows}
