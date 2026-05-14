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
import time as _time
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
    """解析间隔表达式（含极简 + 标准 cron）。失败/负数默认 7 天。

    支持：
    - `every Nm/Nh/Nd`、`Nm/Nh/Nd`（极简）
    - `M H D Mon DoW` 5 段 cron 标准语法（用 CroniterTrigger 估下次触发；失败回退 7 天）

    返回的是"下一次执行需要等多久"，调用方加到 _utcnow() 即可得 next_run_at。
    """
    e = (expr or "").strip().lower()
    if not e:
        return timedelta(days=7)
    if e.startswith("every "):
        e = e[len("every "):].strip()
    # 极简单位
    try:
        n: Optional[int] = None
        unit = e[-1] if e else ""
        if unit in ("m", "h", "d") and e[:-1].lstrip("-").isdigit():
            n = int(e[:-1])
            if n <= 0:
                return timedelta(days=7)
            if unit == "m":
                return timedelta(minutes=n)
            if unit == "h":
                return timedelta(hours=n)
            return timedelta(days=n)
    except ValueError:
        pass
    # 标准 cron：用 APScheduler CronTrigger 算下次触发
    if len(e.split()) == 5:
        try:
            from apscheduler.triggers.cron import CronTrigger
            from datetime import timezone as _tz
            trig = CronTrigger.from_crontab(e, timezone=_tz.utc)
            now_aware = datetime.now(_tz.utc)
            nxt = trig.get_next_fire_time(None, now_aware)
            if nxt is not None:
                delta = nxt - now_aware
                if delta.total_seconds() > 0:
                    return delta
        except Exception:
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

    _MAX_TARGET_KEYS = 16
    _MAX_TARGET_STR_LEN = 1024

    @staticmethod
    def _validate_target(type: str, target: dict) -> None:
        if not isinstance(target, dict):
            raise ValueError("target must be a dict")
        # 防止 megabyte 级 dict / 嵌套炸弹
        if len(target) > SubscriptionService._MAX_TARGET_KEYS:
            raise ValueError(f"target has too many keys (>{SubscriptionService._MAX_TARGET_KEYS})")
        for k, v in target.items():
            if not isinstance(k, str) or len(k) > 64:
                raise ValueError("target keys must be short strings")
            if isinstance(v, str) and len(v) > SubscriptionService._MAX_TARGET_STR_LEN:
                raise ValueError(f"target value too long for key {k!r}")
            if isinstance(v, (list, dict)) and len(str(v)) > 4096:
                raise ValueError(f"target nested value too large for key {k!r}")
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
        """扫一次 due subscriptions，逐个执行 + 立即 commit（订阅之间独立）。

        返回 {ran, found, errors}。仅在调度器内调用；HTTP 路由不应直接调（耗时）。

        事务策略：每个订阅独立 commit / rollback，避免一个订阅失败连带丢失另一个
        订阅的 last_run_at 写入。owns 模式下用自管 session；外部传入 session 时
        调用方负责事务边界，但本方法仍按 sub 边界 flush/rollback（不主动 commit）。
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
                exec_ok = False
                try:
                    n = self._execute_one(session, sub)
                    found += n
                    ran += 1
                    exec_ok = True
                except Exception as e:
                    _log.warning("[subscription %d] %s failed: %s", sub.id, sub.type, e)
                    errors += 1
                    # 部分订阅 _execute_one 可能让 session 进入异常态；先回滚再写元数据
                    if owns:
                        session.rollback()
                # 元数据更新（last_run_at / next_run_at）放在 try 外、独立 try
                try:
                    now2 = _utcnow()
                    sub.last_run_at = now2
                    sub.next_run_at = now2 + parse_simple_interval(sub.cron_expr)
                    if owns:
                        session.commit()
                    else:
                        session.flush()
                except Exception as e:
                    _log.exception("[subscription %d] metadata update failed: %s",
                                   sub.id, e)
                    if owns:
                        session.rollback()
                    errors += 1
                    if exec_ok:
                        ran -= 1  # 若 metadata 写失败，本轮不算 ran 成功
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

    @staticmethod
    def _result_dedup_key(item: dict) -> tuple:
        """返回 (kind, value) 去重键：有 DOI 用 DOI，否则用 (title, year)。"""
        doi = (item.get("doi") or "").strip().lower()
        if doi:
            return ("doi", doi)
        title = (item.get("title") or "").strip().lower()
        year = item.get("year")
        if title:
            return ("ty", title, year)
        return ("none", id(item))  # 无信息量：用 id 保证每次都进入，但不真正重复入库

    def _materialize_citing(
        self,
        session: Session,
        sub: models.Subscription,
        citing_papers: list[dict],
    ) -> int:
        """把 forward-track 返回的 citing_papers 落到 subscription_results。

        去重：同 subscription 下，按 (DOI) 或 (title, year) 去重。无 DOI 也无 title
        的 item 跳过（无信息量）。
        历史去重集仅 select 必要字段（raw_metadata_json 整列），订阅长期运行的代价
        可接受；超大规模时可加 results 上 (subscription_id, doi) 索引。
        """
        if not citing_papers:
            return 0
        seen: set = set()
        rows = session.execute(
            select(models.SubscriptionResult.raw_metadata_json).where(
                models.SubscriptionResult.subscription_id == sub.id,
            )
        ).all()
        for (meta,) in rows:
            key = self._result_dedup_key(meta or {})
            if key[0] != "none":
                seen.add(key)

        new = 0
        for item in citing_papers:
            key = self._result_dedup_key(item)
            if key[0] == "none":
                continue  # 没 DOI 没 title 的丢弃
            if key in seen:
                continue
            session.add(models.SubscriptionResult(
                subscription_id=sub.id,
                paper_id=None,
                raw_metadata_json=item,
                notified=False,
            ))
            seen.add(key)
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

    def _daily_forward_track():
        """每日凌晨 3 点：依次刷新所有有 DOI 论文的前向追踪缓存，限速 1 req/s。
        最多运行 20 小时，防止跨越下一次调度窗口。
        """
        # 延迟导入避免循环引用（subscription_service 与 forward_track_service 互相依赖）
        from services.forward_track_service import ForwardTrackService

        _MAX_RUNTIME = 20 * 3600  # 20 小时上限

        session = SessionLocal()
        try:
            dois = [
                row[0] for row in session.execute(
                    select(models.Paper.doi)
                    .where(models.Paper.doi.isnot(None))
                    .where(models.Paper.doi != "")
                    .where(models.Paper.is_core.is_(True))
                ).all()
            ]
        finally:
            session.close()

        # 过滤纯空白 DOI
        dois = [d for d in dois if d.strip()]

        svc = ForwardTrackService()
        _log.info("daily_forward_track start: %d papers", len(dois))
        start = _time.monotonic()
        for i, doi in enumerate(dois):
            if _time.monotonic() - start > _MAX_RUNTIME:
                _log.warning("daily_forward_track: max runtime reached, stopped at %d/%d", i, len(dois))
                break
            try:
                svc.track(doi, refresh=True)
            except Exception as exc:
                _log.warning("daily_forward_track failed doi=%s err=%s", doi, exc)
            _time.sleep(1)
        _log.info("daily_forward_track done")

    sched.add_job(
        _daily_forward_track,
        trigger="cron",
        hour=3, minute=0,
        id="kb-daily-forward-track",
        replace_existing=True,
        misfire_grace_time=3600,
    )

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
