"""TaskQueue —— 基于 `tasks` 表的任务队列（M1.4）。

替代 `papers/_manifest.json` 作为状态真相源。支持：
- enqueue / fetch_next / mark_running / mark_done / mark_failed
- 启动时 reset_stale：扫 `running` → 重置为 `queued`（崩溃恢复）
- 自动重试：失败任务 attempt < max_attempts 时回排队

与 _manifest.json 共存：M1.4 期间双写（manifest 仍由 expand.py 维护），
未来 milestone 完成切换后移除 manifest 入口。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from database import models


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

    def fetch_next(self, type: Optional[str] = None) -> Optional[models.Task]:
        """取一个待执行任务并标记 running。FIFO（按 id）。"""
        stmt = (
            select(models.Task)
            .where(models.Task.status == "queued")
            .order_by(models.Task.id.asc())
            .limit(1)
        )
        if type:
            stmt = stmt.where(models.Task.type == type)
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
        task.error_log = (task.error_log or "") + f"\n[attempt {task.attempt}] {error}"
        task.finished_at = _utcnow()
        if task.attempt < task.max_attempts:
            task.status = "queued"
            task.started_at = None
            task.finished_at = None
        else:
            task.status = "failed"
        self.session.flush()

    # ─── 崩溃恢复 ────────────────────────────────────────────────────

    def reset_stale(self) -> int:
        """把所有 status=running 的任务重置为 queued。返回受影响行数。"""
        stmt = (
            update(models.Task)
            .where(models.Task.status == "running")
            .values(status="queued", started_at=None)
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount or 0

    # ─── 查询 ────────────────────────────────────────────────────────

    def count_by_status(self) -> dict[str, int]:
        from sqlalchemy import func as sa_func
        rows = self.session.execute(
            select(models.Task.status, sa_func.count(models.Task.id))
            .group_by(models.Task.status)
        ).all()
        return {status: int(count) for status, count in rows}
