"""EasyScholar 期刊等级查询服务。

- 按期刊名查 API，结果缓存到 journals.easyscholar_json
- 超过 CACHE_TTL_DAYS 天自动视为过期，下次调用时刷新
- 调用速率限制：每次请求后 sleep 0.5s（API 限制 2次/秒）
- 展示字段：sci / ssci / sciif / sciUp / sciUpTop / ccf / cssci
"""
from __future__ import annotations

import logging
import os
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import models

_log = logging.getLogger(__name__)

_API_URL = "https://www.easyscholar.cc/open/getPublicationRank"
_CACHE_TTL_DAYS = 180
_RATE_SLEEP = 0.5  # 每次请求后等待，保证 ≤2次/秒

# 展示的字段及中文标签
DISPLAY_FIELDS: list[tuple[str, str]] = [
    ("sci",       "SCI"),
    ("ssci",      "SSCI"),
    ("sciif",     "IF"),
    ("sciUp",     "中科院"),
    ("sciUpTop",  "Top"),
    ("ccf",       "CCF"),
    ("cssci",     "CSSCI"),
]


def _secret_key() -> str:
    return os.environ.get("EASYSCHOLAR_SECRET_KEY", "")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_stale(fetched_at: Optional[datetime]) -> bool:
    if fetched_at is None:
        return True
    return _utcnow() - fetched_at > timedelta(days=_CACHE_TTL_DAYS)


def fetch_from_api(journal_name: str) -> Optional[dict]:
    """调 EasyScholar API，返回 officialRank.all 字典，失败返回 None。"""
    key = _secret_key()
    if not key:
        _log.warning("[easyscholar] EASYSCHOLAR_SECRET_KEY not set")
        return None
    encoded = urllib.parse.quote(journal_name, safe="")
    try:
        resp = httpx.get(
            f"{_API_URL}?secretKey={key}&publicationName={encoded}",
            timeout=15,
        )
        time.sleep(_RATE_SLEEP)
        if resp.status_code != 200:
            _log.warning("[easyscholar] HTTP %s for %s", resp.status_code, journal_name)
            return None
        data = resp.json()
        if data.get("code") != 200:
            _log.warning("[easyscholar] API error %s: %s", data.get("code"), data.get("msg"))
            return None
        return (data.get("data") or {}).get("officialRank", {}).get("all") or {}
    except Exception as exc:
        _log.warning("[easyscholar] request failed for %s: %s", journal_name, exc)
        return None


def get_or_fetch(session: Session, journal: models.Journal) -> Optional[dict]:
    """从缓存取或调 API 取，结果写回 journal 行。"""
    if not _is_stale(journal.easyscholar_fetched_at):
        return journal.easyscholar_json

    result = fetch_from_api(journal.name)
    journal.easyscholar_json = result
    journal.easyscholar_fetched_at = _utcnow()
    try:
        session.flush()
    except Exception as exc:
        _log.warning("[easyscholar] flush failed: %s", exc)
    return result


def get_by_name(session: Session, venue_name: str) -> Optional[dict]:
    """按期刊名查缓存（或调 API），不要求 journal 已关联 paper。"""
    if not venue_name:
        return None
    journal = session.execute(
        select(models.Journal).where(models.Journal.name == venue_name)
    ).scalar_one_or_none()

    if journal is None:
        # 期刊不在库里，直接调 API，不存库（避免污染 journals 表）
        if not _secret_key():
            return None
        result = fetch_from_api(venue_name)
        return result

    return get_or_fetch(session, journal)


def extract_badges(raw: Optional[dict]) -> list[dict]:
    """从 officialRank.all 提取要展示的字段，返回 [{label, value}]。"""
    if not raw:
        return []
    badges = []
    for field, label in DISPLAY_FIELDS:
        val = raw.get(field)
        if val:
            badges.append({"label": label, "value": str(val)})
    return badges


def backfill_stale(session: Session, max_per_run: int = 50) -> dict:
    """夜间流水线调用：刷新 easyscholar 数据过期或缺失的期刊。"""
    cutoff = _utcnow() - timedelta(days=_CACHE_TTL_DAYS)
    from sqlalchemy import or_
    journals = session.execute(
        select(models.Journal)
        .where(
            or_(
                models.Journal.easyscholar_fetched_at.is_(None),
                models.Journal.easyscholar_fetched_at < cutoff,
            )
        )
        .limit(max_per_run)
    ).scalars().all()

    success = failed = 0
    for j in journals:
        result = fetch_from_api(j.name)
        if result is not None:
            j.easyscholar_json = result
            j.easyscholar_fetched_at = _utcnow()
            success += 1
        else:
            failed += 1
        try:
            session.commit()
        except Exception:
            session.rollback()
            failed += 1

    _log.info("[easyscholar] backfill done: success=%d failed=%d", success, failed)
    return {"success": success, "failed": failed}
