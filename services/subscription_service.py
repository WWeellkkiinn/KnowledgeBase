"""SubscriptionService —— 订阅管理（M2.3）。

三种订阅类型（PLAN.md §3 subscriptions.type）：
- `paper_citations`: target={"doi": "..."} —— 监控某 DOI 的新被引（走 ForwardTrackService）
- `author_works`: target={"author_id": "openalex:Axxx"} —— 监控某作者新作
- `topic_search`: target={"query": "...", "focus": "..."} —— 关键词新论文

调度模型：单进程 APScheduler BackgroundScheduler（threading 模式，对齐 Flask-SocketIO）。
- 在 Flask app 启动时调用 `start_scheduler(app, socketio=None)` 初始化全局 scheduler
- scheduler 持有一个 cron job：每分钟扫一次 subscriptions 表，把 next_run_at <= now 的拉出来执行
- 个别订阅的 cron_expr 用于计算 next_run_at（每次执行后续写）

并发：单 scheduler 实例 + 单 worker 线程（max_workers=1 默认），保证不会两个 subscription
同时跑（避免 SS 配额被瞬间耗尽）。

幂等：subscription_results.notified=False 表示未读；调用方按 (subscription_id, paper.doi)
去重避免重复写入。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal, models

_log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── cron 表达式（最小子集；完整解析交给 APScheduler）─────────────────
# 这里只在没装 APScheduler 时用作 fallback，计算下一次执行时间。
# 支持："every Nm/Nh/Nd" 简化语法 + 默认 7 天。
def parse_simple_interval(expr: str) -> timedelta:
    """解析极简间隔表达式。失败默认 7 天。

    APScheduler 标准 cron 语法 ("0 3 * * 1") 不在此处解析 —— 由
    add_subscription_job() 直接喂给 CronTrigger.from_crontab。
    """
    e = (expr or "").strip().lower()
    if e.startswith("every "):
        e = e[len("every "):].strip()
    try:
        if e.endswith("m"):
            return timedelta(minutes=int(e[:-1]))
        if e.endswith("h"):
            return timedelta(hours=int(e[:-1]))
        if e.endswith("d"):
            return timedelta(days=int(e[:-1]))
    except ValueError:
        pass
    return timedelta(days=7)


# ─── CRUD ──────────────────────────────────────────────────────────


class SubscriptionService:
    def __init__(self, db_session: Optional[Session] = None) -> None:
        self.db_session = db_session

    # 列表 / 详情

    @staticmethod
    def list_all(session: Session, *, active_only: bool = False) -> list[models.Subscription]:
        stmt = select(models.Subscription).order_by(models.Subscription.id.asc())
        if active_only:
            stmt = stmt.where(models.Subscription.active.is_(True))
        return list(session.execute(stmt).scalars().all())

    @staticmethod
    def get(session: Session, sub_id: int) -> Optional[models.Subscription]:
        return session.get(models.Subscription, sub_id)

    # 创建 / 更新 / 删除

    def create(
        self,
        session: Session,
        *,
        type: str,
        target: dict,
        cron_expr: str,
        active: bool = True,
    ) -> models.Subscription:
        if type not in ("paper_citations", "author_works", "topic_search"):
            raise ValueError(f"unsupported subscription type: {type!r}")
        self._validate_target(type, target)
        sub = models.Subscription(
            type=type,
            target_json=dict(target),
            cron_expr=cron_expr,
            active=active,
            next_run_at=_utcnow() + parse_simple_interval(cron_expr),
        )
        session.add(sub)
        session.flush()
        return sub

    @staticmethod
    def update(
        session: Session,
        sub_id: int,
        *,
        cron_expr: Optional[str] = None,
        active: Optional[bool] = None,
        target: Optional[dict] = None,
    ) -> Optional[models.Subscription]:
        sub = session.get(models.Subscription, sub_id)
        if sub is None:
            return None
        if cron_expr is not None:
            sub.cron_expr = cron_expr
            sub.next_run_at = _utcnow() + parse_simple_interval(cron_expr)
        if active is not None:
            sub.active = bool(active)
        if target is not None:
            SubscriptionService._validate_target(sub.type, target)
            sub.target_json = dict(target)
        session.flush()
        return sub

    @staticmethod
    def delete(session: Session, sub_id: int) -> bool:
        sub = session.get(models.Subscription, sub_id)
        if sub is None:
            return False
        session.delete(sub)
        session.flush()
        return True

    # 验证 target_json 形状

    @staticmethod
    def _validate_target(type: str, target: dict) -> None:
        if not isinstance(target, dict):
            raise ValueError("target must be a dict")
        if type == "paper_citations":
            if not target.get("doi"):
                raise ValueError("paper_citations target requires 'doi'")
        elif type == "author_works":
            if not target.get("author_id"):
                raise ValueError("author_works target requires 'author_id'")
        elif type == "topic_search":
            if not target.get("query"):
                raise ValueError("topic_search target requires 'query'")

    # ─── 执行 ─────────────────────────────────────────────────────

    def run_due(self, session: Optional[Session] = None) -> dict:
        """扫一次 due subscriptions，逐个执行。

        返回 {ran, found, errors}。仅在调度器内调用；HTTP 路由不应直接调（耗时）。
        """
        owns = session is None
        session = session or SessionLocal()
        try:
            now = _utcnow()
            stmt = select(models.Subscription).where(
                models.Subscription.active.is_(True),
                models.Subscription.next_run_at <= now,
            )
            due = list(session.execute(stmt).scalars().all())
            ran = errors = found = 0
            for sub in due:
                try:
                    n = self._execute_one(session, sub)
                    found += n
                    ran += 1
                except Exception as e:
                    _log.warning("[subscription %d] %s failed: %s", sub.id, sub.type, e)
                    errors += 1
                finally:
                    sub.last_run_at = _utcnow()
                    sub.next_run_at = _utcnow() + parse_simple_interval(sub.cron_expr)
                    session.flush()
            if owns:
                session.commit()
            return {"ran": ran, "found": found, "errors": errors}
        except Exception:
            if owns:
                session.rollback()
            raise
        finally:
            if owns:
                session.close()

    def _execute_one(self, session: Session, sub: models.Subscription) -> int:
        """执行一个订阅，把新发现的项写入 subscription_results。返回新增条数。"""
        tgt = dict(sub.target_json or {})
        if sub.type == "paper_citations":
            from services.forward_track_service import ForwardTrackService
            result = ForwardTrackService(db_session=session).track(tgt["doi"])
            return self._materialize_citing(session, sub, result.get("citing_papers", []))
        if sub.type == "author_works":
            # M2.3 阶段先记录 placeholder；实际抓取留给后续 milestone（避免引入 OpenAlex
            # author 列表 API 的额外复杂度，先保证调度通路）
            _log.info("[subscription %d] author_works not yet implemented", sub.id)
            return 0
        if sub.type == "topic_search":
            _log.info("[subscription %d] topic_search not yet implemented", sub.id)
            return 0
        return 0

    def _materialize_citing(
        self,
        session: Session,
        sub: models.Subscription,
        citing_papers: list[dict],
    ) -> int:
        """把 forward-track 返回的 citing_papers 落到 subscription_results。

        去重策略：同 subscription 下，新发现的 paper.doi 与历史 results 中的 doi 不重复。
        """
        if not citing_papers:
            return 0
        seen = set()
        existing = session.execute(
            select(models.SubscriptionResult).where(
                models.SubscriptionResult.subscription_id == sub.id,
            )
        ).scalars().all()
        for r in existing:
            doi = (r.raw_metadata_json or {}).get("doi", "")
            if doi:
                seen.add(doi)

        new = 0
        for item in citing_papers:
            doi = item.get("doi", "")
            if doi and doi in seen:
                continue
            session.add(models.SubscriptionResult(
                subscription_id=sub.id,
                paper_id=None,
                raw_metadata_json=item,
                notified=False,
            ))
            if doi:
                seen.add(doi)
            new += 1
        session.flush()
        return new


# ─── APScheduler 集成 ──────────────────────────────────────────────


_scheduler = None  # 全局单例（每进程一份）


def start_scheduler(*, poll_seconds: int = 60) -> object:
    """启动 BackgroundScheduler。在 Flask app create 之后调用一次。

    重复调用是安全的：已 running 则直接返回现有实例。
    """
    global _scheduler
    if _scheduler is not None and getattr(_scheduler, "running", False):
        return _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError as e:
        _log.warning("APScheduler not installed; subscription scheduler disabled (%s)", e)
        return None

    sched = BackgroundScheduler(
        timezone="UTC",
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
    )

    def _tick():
        try:
            SubscriptionService().run_due()
        except Exception as e:
            _log.exception("[scheduler tick] %s", e)

    sched.add_job(_tick, "interval", seconds=poll_seconds, id="kb-subscriptions-tick",
                  replace_existing=True)
    sched.start()
    _scheduler = sched
    _log.info("subscription scheduler started (poll %ds)", poll_seconds)
    return sched


def stop_scheduler() -> None:
    """关闭 scheduler。Flask 进程退出时调用，测试也用。"""
    global _scheduler
    if _scheduler is not None and getattr(_scheduler, "running", False):
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
    _scheduler = None
