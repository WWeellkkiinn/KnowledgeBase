"""SQLAlchemy ORM 模型 —— 对齐 PLAN.md §3 schema。

8 张表：
  papers / journals / edges / tasks / subscriptions /
  subscription_results / citations / sessions

实现注意：
- DateTime 一律 naive UTC：SQLite 不真正保存时区信息，强行写 timezone=True 会造成
  naive/aware 混用陷阱。约定：写入侧统一用 `datetime.now(timezone.utc).replace(tzinfo=None)`，
  读出后视为 UTC。
- PLAN §3 中的列 `index` 在 ORM 落地为 `ref_index`（`index` 是 SQL 关键字）。
- JSON 列中可能 in-place 修改的字段（payload_json / target_json）用 MutableDict 包装。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base

MutableJSON = MutableDict.as_mutable(JSON)


class Journal(Base):
    __tablename__ = "journals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issn: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(512))
    publisher: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    quality_tier: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-4
    is_predatory: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0"), nullable=False
    )
    oa_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    source_dataset: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    refreshed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    easyscholar_json: Mapped[Optional[dict]] = mapped_column(MutableJSON, nullable=True)
    easyscholar_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stem: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    doi: Mapped[Optional[str]] = mapped_column(String(256), unique=True, nullable=True, index=True)
    arxiv_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    authors_json: Mapped[Optional[list]] = mapped_column(MutableList.as_mutable(JSON), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    journal_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("journals.id", ondelete="SET NULL"), nullable=True
    )
    pdf_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    md_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    sha1: Mapped[Optional[str]] = mapped_column(String(40), unique=True, nullable=True, index=True)
    insight_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    refs_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", server_default=text("'pending'"), nullable=False
    )  # pending|analyzed|failed
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(32), default="ref", server_default=text("'ref'"), nullable=False
    )  # root|ref|forward|subscription
    is_core: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0"), nullable=False, index=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    tags: Mapped[Optional[list]] = mapped_column(MutableList.as_mutable(JSON), nullable=True)
    ai_summary: Mapped[Optional[dict]] = mapped_column(MutableJSON, nullable=True)
    ai_analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # lazy="select"（默认）—— 列表场景不强制 JOIN，详情场景按需访问
    journal: Mapped[Optional[Journal]] = relationship(Journal, lazy="select")


class Edge(Base):
    __tablename__ = "edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    to_paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # backward|forward
    # PLAN §3 的 `index`：backward 边来自分析序号；forward 边可能没有，因此允许 NULL
    ref_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ref_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )

    __table_args__ = (
        # 仅对 ref_index 非空的边强制 "(from, direction, ref_index) 唯一"；
        # SQLite partial index 在 migration 里手写（Alembic autogenerate 不支持 partial）。
        UniqueConstraint("from_paper_id", "direction", "ref_index", name="uq_edge_indexed"),
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    paper_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("papers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    payload_json: Mapped[Optional[dict]] = mapped_column(MutableJSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="queued", server_default=text("'queued'"), nullable=False, index=True
    )
    attempt: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, default=3, server_default=text("3"), nullable=False
    )
    parent_task_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # paper_citations|author_works|topic_search
    target_json: Mapped[dict] = mapped_column(MutableJSON, nullable=False)
    cron_expr: Mapped[str] = mapped_column(String(64), nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1"), nullable=False, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_queries: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    last_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    query_refreshed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    query_stats_json: Mapped[Optional[dict]] = mapped_column(MutableJSON, nullable=True)


class SubscriptionResult(Base):
    """订阅结果行。

    llm_score / llm_reason / scored_at：LLM 相关性评分字段，由 score_pending_results 写入。
    """

    __tablename__ = "subscription_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("papers.id", ondelete="SET NULL"), nullable=True
    )
    raw_metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    notified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0"), nullable=False
    )
    found_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    llm_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    llm_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scored_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    title_zh: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    research_question: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    methodology: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_findings_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    citation_key: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    bibtex: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    apa: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refreshed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class SessionRecord(Base):
    """对应 papers/<stem>/session_*.jsonl 的索引。"""
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    jsonl_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    phase: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ForwardTrackCache(Base):
    """前向追踪结果缓存（PLAN §8 risks：同 DOI 7 天内不重查）。

    缓存键是归一化后的 DOI（小写、剥 https://doi.org/ 前缀），与 paper_id 解耦，
    同一 DOI 多次查询共享一份缓存。SS 免费配额 100 req/5min，OpenAlex 无限速但
    并发不稳定，缓存是 M2.3 订阅周期跑批前的必要保护。
    """

    __tablename__ = "forward_track_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doi: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )


class BackwardTrackCache(Base):
    """后向追踪结果缓存：这篇论文引用了哪些论文（与 ForwardTrackCache 对称）。"""

    __tablename__ = "backward_track_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doi: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )


Index("ix_tasks_status_type", Task.status, Task.type)
Index("ix_subscriptions_active_next", Subscription.active, Subscription.next_run_at)
# /api/papers?status=&source= 常见过滤路径
Index("ix_papers_status", Paper.status)
Index("ix_papers_source", Paper.source)


__all__ = [
    "Paper",
    "Journal",
    "Edge",
    "Task",
    "Subscription",
    "SubscriptionResult",
    "Citation",
    "SessionRecord",
    "ForwardTrackCache",
    "BackwardTrackCache",
]

# 触发 SQLAlchemy 注册 UserProfile / Recommendation 到同一个 Base.metadata，
# 让 alembic autogen 与 Base.metadata.create_all 都能看到这两张表。
from database import models_recs  # noqa: F401,E402
