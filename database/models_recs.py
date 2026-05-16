"""LLM 推荐功能 ORM —— user_profile 单行画像 + recommendations 推荐流水。

复用 `database.models.Base` 的 metadata，让 alembic autogenerate 能识别这两张表。
所有 DateTime 一律 naive UTC（写入侧 `datetime.now(timezone.utc).replace(tzinfo=None)`），
与项目既有模式对齐。
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Integer,
    Text,
)

from database.models import Base


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UserProfile(Base):
    """用户兴趣画像（单行表）。

    profile_json schema:
        {
          "themes": [
            {"name", "keywords_en": [...], "keywords_zh": [...],
             "key_authors": [...], "methods": [...], "weight": float},
            ...
          ],
          "excluded": [str, ...]
        }
    """

    __tablename__ = "user_profile"
    __table_args__ = (
        CheckConstraint("id = 1", name="user_profile_single_row"),
    )

    id = Column(Integer, primary_key=True)
    profile_json = Column(JSON, nullable=False)
    generated_at = Column(DateTime, nullable=False)
    source_paper_count = Column(Integer, nullable=False, default=0)
    model = Column(Text, nullable=False)


class Recommendation(Base):
    """LLM 评分后写入的推荐项。external_id 唯一防重复入库。"""

    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(Text, unique=True, nullable=False)  # doi 或 arxiv:xxx
    source = Column(Text, nullable=False)  # openalex / semantic_scholar / arxiv
    title = Column(Text, nullable=False)
    abstract = Column(Text)
    authors_json = Column(JSON)
    year = Column(Integer)
    url = Column(Text)
    matched_theme = Column(Text)
    relevance_score = Column(Float, nullable=False)
    reason = Column(Text)
    created_at = Column(DateTime, nullable=False, default=_utcnow_naive)
    dismissed = Column(Boolean, nullable=False, default=False)
    saved_to_library = Column(Boolean, nullable=False, default=False)


__all__ = ["UserProfile", "Recommendation"]
