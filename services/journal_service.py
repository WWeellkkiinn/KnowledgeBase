"""JournalService —— 期刊质量评分（M2.2）。

设计：
- 静态 seed (database/seed/journals.json) 覆盖核心期刊（ABM / 经济 / 管理）
- OpenAlex 兜底：传入 paper 的 DOI，从 OpenAlex `primary_location.source` 抽期刊
- 字段：issn / name / publisher / quality_tier(1-4) / is_predatory / oa_status
- Tier 未知时返回 None；前端按需显示 "Unknown"

并发：bootstrap_from_seed 用 INSERT-OR-IGNORE 语义（先查后插），同 ISSN 多线程
重复 upsert 时可能因 unique 约束抛 IntegrityError，调用方应捕获或在主线程一次性
初始化（推荐：app create 阶段或 backfill 脚本里串行调用）。

不主动写 paper.journal_id：attach_to_paper 显式调用方决定何时落库（避免在分析
流水线里偷偷改 schema 状态，保持 service 边界）。
"""
from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import hashlib

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import models

from ._paths import ROOT, ensure_scripts_on_path

_log = logging.getLogger(__name__)

SEED_PATH = ROOT / "database" / "seed" / "journals.json"
_OPENALEX_BASE = "https://api.openalex.org"
_TIMEOUT = 30
# 入 DB 前先把 ISSN 规整成 ####-#### 格式；非标准格式（如 EISSN 单串）保留原文
_ISSN_RE = re.compile(r"^\d{4}-\d{3}[\dXx]$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_issn(issn: str) -> str:
    """剥空白 + 末位 X 校验位强制大写（"0305-750x" 与 "0305-750X" 视为同一刊）。"""
    s = (issn or "").strip()
    if _ISSN_RE.match(s):
        return s[:-1] + s[-1].upper()
    return s


def _make_surrogate_issn(name: str) -> str:
    """为没有 ISSN 的期刊生成 16 字符内的稳定 surrogate（满足 Journal.issn 长度上限）。
    格式 `u:<10位 hex>` —— 同名映射到同一 surrogate，避免重复入库。
    """
    digest = hashlib.sha1((name or "").lower().encode("utf-8")).hexdigest()[:10]
    return f"u:{digest}"


def _normalize_name(name: str) -> str:
    """期刊名归一化：小写、去标点（保留字母数字与空格）、压缩空白。"""
    n = (name or "").lower()
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


# ─── name → journal_id 进程内缓存 ──────────────────────────────────
# 首次调用 lookup_by_name 时一次性预加载全表（按 normalize 后的 name 索引），
# 之后 O(1) 命中。attach_to_paper 创建新 Journal 时同步写入，保证缓存最新。
# 进程生命周期内常驻；测试场景如需重置可调用 _reset_name_cache()。
_name_cache: dict[str, int] = {}
_name_cache_loaded: bool = False
_name_cache_lock = threading.Lock()


def _ensure_name_cache(session: Session) -> None:
    """首次调用时全表加载到 _name_cache。线程安全：双检锁。"""
    global _name_cache_loaded
    if _name_cache_loaded:
        return
    with _name_cache_lock:
        if _name_cache_loaded:
            return
        rows = session.execute(select(models.Journal.id, models.Journal.name)).all()
        for jid, jname in rows:
            key = _normalize_name(jname or "")
            if key:
                _name_cache.setdefault(key, jid)
        _name_cache_loaded = True


def _cache_journal_name(name: str, journal_id: int) -> None:
    """新建 Journal 时调用，将 normalize 后的 name 写入缓存。"""
    key = _normalize_name(name or "")
    if not key:
        return
    with _name_cache_lock:
        _name_cache[key] = journal_id


def _reset_name_cache() -> None:
    """测试钩子：清空缓存（生产代码不应调用）。"""
    global _name_cache_loaded
    with _name_cache_lock:
        _name_cache.clear()
        _name_cache_loaded = False


def _openalex_mailto() -> Optional[str]:
    ensure_scripts_on_path()
    try:
        from config import UNPAYWALL_EMAIL  # type: ignore
        return UNPAYWALL_EMAIL or None
    except Exception:
        return None


class JournalService:
    """期刊评分 service。可选 db_session 主要供测试；正式路径让调用方传 session。"""

    def __init__(self, db_session: Optional[Session] = None) -> None:
        self.db_session = db_session

    # ─── seed 引导 ──────────────────────────────────────────────────

    def bootstrap_from_seed(self, session: Session, *, seed_path: Path = SEED_PATH) -> dict:
        """从 seed JSON 把期刊 upsert 入库；返回 {inserted, updated, skipped}。

        幂等：以 ISSN 为唯一键，已存在则更新 name/publisher/quality_tier 等字段。

        防御性：seed 文件缺失、JSON 解析失败、根节点非 list、行非 dict、tier 非 int
        等均不阻塞，记 skipped 后继续；批量损坏时返回 inserted=0 但不抛异常。
        """
        try:
            raw = seed_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            _log.warning("[journal] seed not found: %s", seed_path)
            return {"inserted": 0, "updated": 0, "skipped": 0}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            _log.error("[journal] seed JSON invalid: %s", e)
            return {"inserted": 0, "updated": 0, "skipped": 0}
        if not isinstance(data, list):
            _log.error("[journal] seed root must be a JSON array, got %s", type(data).__name__)
            return {"inserted": 0, "updated": 0, "skipped": 0}

        # 预加载现有 journals → dict，避免 seed 每行触发一次 SELECT
        existing_by_issn = {
            j.issn: j for j in
            session.execute(select(models.Journal)).scalars().all()
        }
        inserted = updated = skipped = 0
        for row in data:
            if not isinstance(row, dict):
                skipped += 1
                continue
            issn = _normalize_issn(str(row.get("issn", "") or ""))
            name = str(row.get("name", "") or "").strip()
            if not issn or not name:
                skipped += 1
                continue
            tier = row.get("quality_tier")
            if tier is not None and (not isinstance(tier, int) or tier < 1 or tier > 4):
                tier = None  # 非法 tier 当 Unknown，不阻塞 seed
            publisher = row.get("publisher")
            if publisher is not None and not isinstance(publisher, str):
                publisher = None
            oa_status = row.get("oa_status")
            if oa_status is not None and not isinstance(oa_status, str):
                oa_status = None
            source_dataset = row.get("source_dataset", "manual")
            if not isinstance(source_dataset, str):
                source_dataset = "manual"

            existing = existing_by_issn.get(issn)
            if existing is None:
                new_j = models.Journal(
                    issn=issn,
                    name=name,
                    publisher=publisher,
                    quality_tier=tier,
                    is_predatory=bool(row.get("is_predatory", False)),
                    oa_status=oa_status,
                    source_dataset=source_dataset,
                    refreshed_at=_utcnow(),
                )
                session.add(new_j)
                session.flush()
                if new_j.id is not None:
                    _cache_journal_name(name, new_j.id)
                inserted += 1
            else:
                existing.name = name
                existing.publisher = publisher or existing.publisher
                if tier is not None:
                    existing.quality_tier = tier
                existing.is_predatory = bool(row.get("is_predatory", existing.is_predatory))
                if oa_status:
                    existing.oa_status = oa_status
                existing.source_dataset = source_dataset
                existing.refreshed_at = _utcnow()
                updated += 1
        session.flush()
        return {"inserted": inserted, "updated": updated, "skipped": skipped}

    # ─── 查询 ───────────────────────────────────────────────────────

    @staticmethod
    def lookup_by_issn(session: Session, issn: str) -> Optional[models.Journal]:
        issn_norm = _normalize_issn(issn)
        if not issn_norm:
            return None
        return session.execute(
            select(models.Journal).where(models.Journal.issn == issn_norm)
        ).scalar_one_or_none()

    @staticmethod
    def lookup_by_name(session: Session, name: str) -> Optional[models.Journal]:
        """名字精确匹配（归一化后）。

        使用模块级 _name_cache：首次调用预加载全表 id+name，之后 O(1) 命中。
        attach_to_paper 创建新 Journal 时会回写缓存，保证后续 lookup 可见。
        """
        n = _normalize_name(name)
        if not n:
            return None
        _ensure_name_cache(session)
        jid = _name_cache.get(n)
        if jid is None:
            return None
        return session.get(models.Journal, jid)

    # ─── OpenAlex 兜底 ──────────────────────────────────────────────

    def fetch_journal_from_doi(self, doi: str) -> Optional[dict]:
        """根据 DOI 拉 OpenAlex 期刊元数据。返回 dict 或 None。

        OpenAlex `primary_location.source` 字段：
          { id, display_name, issn_l, issn, type, host_organization_name, ... }
        我们只取 issn_l(优先) / issn[0] / display_name / host_organization_name。

        DOI 走 ForwardTrackService 同款字符集校验，防 URL 路径注入。
        """
        from .reference_fetcher import normalize_doi
        doi = normalize_doi(doi or "")
        if not doi:
            return None
        mailto = _openalex_mailto()
        params = {"mailto": mailto} if mailto else {}
        try:
            resp = httpx.get(
                f"{_OPENALEX_BASE}/works/doi:{doi}", params=params, timeout=_TIMEOUT
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
        except Exception as e:
            _log.warning("[journal] openalex %s failed: %s", doi, e)
            return None

        src = ((data.get("primary_location") or {}).get("source")) or \
              ((data.get("host_venue")) or None)
        if not src:
            return None
        issns = src.get("issn") or []
        issn = src.get("issn_l") or (issns[0] if issns else "")
        name = (src.get("display_name") or "").strip()
        if not issn and not name:
            return None
        return {
            "issn": _normalize_issn(issn),
            "name": name,
            "publisher": src.get("host_organization_name") or None,
            "oa_status": (data.get("open_access") or {}).get("oa_status") or None,
            "source_dataset": "openalex",
        }

    # ─── 关联到 paper ───────────────────────────────────────────────

    def attach_to_paper(
        self,
        session: Session,
        paper: models.Paper,
        meta: Optional[dict] = None,
    ) -> Optional[models.Journal]:
        """把 paper 链到对应的 Journal。
        meta 为 None 时尝试从 paper.doi 拉 OpenAlex。
        返回链上的 Journal（可能是已有的，可能是新建的，Tier 缺失则 None）。
        """
        if meta is None:
            meta = self.fetch_journal_from_doi(paper.doi or "")
        if not meta:
            return None
        issn = _normalize_issn(meta.get("issn", ""))
        name = (meta.get("name") or "").strip()

        journal: Optional[models.Journal] = None
        if issn:
            journal = self.lookup_by_issn(session, issn)
        if journal is None and name:
            journal = self.lookup_by_name(session, name)

        if journal is None:
            # 新期刊；Tier 留空（OpenAlex 没打分），后续可由人工或外部数据填入
            if not issn and not name:
                return None
            surrogate = issn or _make_surrogate_issn(name)
            journal = models.Journal(
                issn=surrogate,
                name=name or "(unknown)",
                publisher=meta.get("publisher"),
                quality_tier=meta.get("quality_tier"),
                is_predatory=bool(meta.get("is_predatory", False)),
                oa_status=meta.get("oa_status"),
                source_dataset=meta.get("source_dataset", "openalex"),
                refreshed_at=_utcnow(),
            )
            # 用 savepoint 隔离冲突，避免回滚外层事务
            try:
                with session.begin_nested():
                    session.add(journal)
                    session.flush()
            except IntegrityError:
                journal = session.execute(
                    select(models.Journal).where(models.Journal.issn == surrogate)
                ).scalar_one_or_none()
                if journal is None:
                    raise
            # 同步更新 name 缓存，避免下次 lookup_by_name 又走全表
            if journal is not None and journal.id is not None:
                _cache_journal_name(journal.name or name, journal.id)
        else:
            # 已存在：仅在原值为空时填补，避免 OpenAlex 覆盖 manual seed 的 tier
            if journal.quality_tier is None and meta.get("quality_tier") is not None:
                journal.quality_tier = meta["quality_tier"]
            if not journal.oa_status and meta.get("oa_status"):
                journal.oa_status = meta["oa_status"]
            if not journal.publisher and meta.get("publisher"):
                journal.publisher = meta["publisher"]

        paper.journal_id = journal.id
        session.flush()
        return journal

    # ─── 批量补全 ────────────────────────────────────────────────────

    def backfill_journals(self, session: Session) -> dict:
        """对所有核心论文中有 DOI 但未关联期刊的，调用 OpenAlex 补全。

        逐篇同步请求，每篇间隔 1 秒（避免触发 OpenAlex polite pool 限速）。
        返回 {success, failed}。
        """
        import time as _time
        papers = session.execute(
            select(models.Paper)
            .where(models.Paper.doi.isnot(None))
            .where(models.Paper.doi != "")
            .where(models.Paper.journal_id.is_(None))
            .where(models.Paper.is_core.is_(True))
        ).scalars().all()

        success = failed = 0
        for paper in papers:
            try:
                journal = self.attach_to_paper(session, paper)
                if journal:
                    session.commit()
                    success += 1
                else:
                    failed += 1
            except Exception as exc:
                session.rollback()
                _log.warning("[journal] backfill failed doi=%s err=%s", paper.doi, exc)
                failed += 1
            _time.sleep(1)

        _log.info("[journal] backfill done: success=%d failed=%d", success, failed)
        return {"success": success, "failed": failed}
