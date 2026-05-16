"""LLM 兴趣画像生成服务。

每周用 Ollama 把用户库最近 30 篇 high-relevance 论文压成画像 JSON。
画像 schema：{themes: [{name, keywords_en, keywords_zh, key_authors, methods, weight}], excluded: []}

冷启动（已分析论文 < 5）：返回空画像，不写表。
缓存：force=False 且画像 < PROFILE_TTL_DAYS 天，直接返回旧画像。
失败兜底：Ollama 调用/JSON 解析失败不抹掉旧画像，仅 warning + 返回旧画像（或空）。
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import models
from database.models_recs import UserProfile
from services.ai_service import _call_ollama

_log = logging.getLogger(__name__)

PROFILE_TTL_DAYS = 14
COLD_START_MIN = 5
# 减到 20：qwen3.6-27b num_ctx=8K，30 篇 + schema 提示词易截尾导致 JSON 不完整
MAX_SOURCE_PAPERS = 20

# 防止两个 force=True 并发调用都走到 db.add(UserProfile(id=1))，触发主键冲突
_REGEN_LOCK = threading.Lock()
_MODEL = os.environ.get("KB_OLLAMA_MODEL", "qwen3.6-27b")

_SYSTEM = (
    "你是学术研究兴趣画像分析师。给定一批论文（标题、tags、研究问题、方法），"
    "提取用户的研究兴趣。仅输出合法 JSON（不带 markdown 包裹、不带解释）。"
)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _load_profile_row(db: Session) -> UserProfile | None:
    return db.execute(select(UserProfile).where(UserProfile.id == 1)).scalar_one_or_none()


def _build_prompt(papers: list[models.Paper]) -> str:
    items: list[dict[str, Any]] = []
    # 字段截断（防 num_ctx 8K 截尾）：title/research_question/methodology 各 200 字符，tags 取前 5
    for p in papers:
        summary = p.ai_summary or {}
        items.append({
            "title": (p.title or "")[:200],
            "tags": (p.tags or [])[:5],
            "research_question": str(summary.get("research_question", ""))[:200],
            "methodology": str(summary.get("methodology", ""))[:200],
        })
    schema_hint = (
        '{"themes": ['
        '{"name": "主题名（中文）",'
        '"keywords_en": ["english keyword 1", "english keyword 2"],'
        '"keywords_zh": ["中文关键词1", "中文关键词2"],'
        '"key_authors": ["author 1"],'
        '"methods": ["方法1"],'
        '"weight": 0.0}'
        '], "excluded": ["明显无关的主题"]}'
    )
    return (
        "以下是用户库中的论文（JSON 数组）：\n"
        f"{json.dumps(items, ensure_ascii=False, indent=2)}\n\n"
        "请总结用户的研究兴趣，识别 3-6 个主要 theme，每个 theme 给出：\n"
        "- name: 主题名（中文）\n"
        "- keywords_en: 用于外部 API 搜索的英文关键词（2-5 个）\n"
        "- keywords_zh: 中文关键词（2-5 个）\n"
        "- key_authors: 该主题下出现频繁的核心作者（0-5 个）\n"
        "- methods: 主要研究方法（0-3 个）\n"
        "- weight: 该主题在用户库中的权重（0.0-1.0，所有 theme 权重之和约为 1.0）\n"
        "另外列出用户明确不感兴趣的主题（excluded）。\n\n"
        f"严格按此 schema 输出：\n{schema_hint}"
    )


_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _clean_str(x: Any, maxlen: int) -> str:
    s = str(x).strip()
    s = _CTRL_RE.sub("", s)
    return s[:maxlen]


def _clean_list(raw: Any, maxlen: int, item_maxlen: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for k in raw[:maxlen]:
        if isinstance(k, (str, int)):
            out.append(_clean_str(k, item_maxlen))
    return out


def _parse_profile_json(raw: str) -> dict | None:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    themes_raw = data.get("themes")
    if not isinstance(themes_raw, list):
        return None
    themes: list[dict] = []
    # 限制 themes 数量 + 每个 theme 内列表/字符串 size cap，防 LLM 输出爆膨胀
    for t in themes_raw[:10]:
        if not isinstance(t, dict):
            continue
        themes.append({
            "name": _clean_str(t.get("name") or "", 200),
            "keywords_en": _clean_list(t.get("keywords_en"), 10, 50),
            "keywords_zh": _clean_list(t.get("keywords_zh"), 10, 50),
            "key_authors": _clean_list(t.get("key_authors"), 10, 50),
            "methods": _clean_list(t.get("methods"), 10, 50),
            "weight": float(t.get("weight") or 0.0),
        })
    excluded = _clean_list(data.get("excluded") or [], 10, 100)
    return {"themes": themes, "excluded": excluded}


def regenerate_profile(db: Session, *, force: bool = False) -> dict:
    """读最近 ai_analyzed_at 的论文 → 调 LLM 生成画像 → upsert user_profile。

    冷启动：< COLD_START_MIN 篇返回 {"themes": [], "excluded": []}（不写表）。
    缓存：force=False 且现有画像 < PROFILE_TTL_DAYS 天，直接返回缓存。
    失败：不写新画像，返回旧画像（或空）。
    """
    # 并发锁：两个 force=True 同时进入会都走到 db.add(UserProfile(id=1)) 触发主键冲突
    with _REGEN_LOCK:
        existing = _load_profile_row(db)

        # existing.generated_at 理论上 NOT NULL，但 race / 手工补数据时可能 None
        if (
            not force
            and existing is not None
            and existing.generated_at is not None
        ):
            age = _utcnow_naive() - existing.generated_at
            if age < timedelta(days=PROFILE_TTL_DAYS):
                _log.info("profile cache hit (age=%s), skip regenerate", age)
                return existing.profile_json

        papers = db.execute(
            select(models.Paper)
            .where(models.Paper.ai_analyzed_at.isnot(None))
            .order_by(models.Paper.ai_analyzed_at.desc())
            .limit(MAX_SOURCE_PAPERS)
        ).scalars().all()

        if len(papers) < COLD_START_MIN:
            _log.info("cold start: only %d analyzed papers (need >= %d)", len(papers), COLD_START_MIN)
            return {"themes": [], "excluded": []}

        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _build_prompt(papers)},
        ]
        try:
            raw = _call_ollama(messages, num_predict=4096)
        except Exception as exc:
            _log.warning("regenerate_profile ollama error: %s", exc)
            return existing.profile_json if existing else {"themes": [], "excluded": []}

        parsed = _parse_profile_json(raw)
        if parsed is None:
            _log.warning("regenerate_profile: failed to parse JSON from response: %.200s", raw)
            return existing.profile_json if existing else {"themes": [], "excluded": []}

        now = _utcnow_naive()
        if existing is None:
            row = UserProfile(
                id=1,
                profile_json=parsed,
                generated_at=now,
                source_paper_count=len(papers),
                model=_MODEL,
            )
            db.add(row)
        else:
            existing.profile_json = parsed
            existing.generated_at = now
            existing.source_paper_count = len(papers)
            existing.model = _MODEL

        try:
            db.commit()
        except Exception as exc:
            # commit 失败：existing 的内存值已被改脏，回退原值无意义；
            # 直接 rollback + raise，由 APScheduler / 调用方决定重试或告警
            db.rollback()
            _log.exception("regenerate_profile commit error: %s", exc)
            raise

        _log.info("profile regenerated: %d themes, source=%d papers", len(parsed.get("themes", [])), len(papers))
        return parsed


__all__ = ["regenerate_profile", "PROFILE_TTL_DAYS", "COLD_START_MIN"]
