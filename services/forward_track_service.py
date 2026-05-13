"""ForwardTrackService —— 前向追踪（M2.1）。

输入一篇论文的 DOI，返回"哪些论文引用了它"。双源：
- Semantic Scholar `paper/DOI:{doi}/citations`（免费 100 req/5min，元数据丰富）
- OpenAlex `works?filter=cites:{openalex_id}`（无限速，量大）

结果按 DOI（小写归一化）去重合并，没 DOI 的按 (title, year) 兜底。

缓存：写 `forward_track_cache` 表，同 DOI 7 天内不重查（PLAN §8 风险表已锁）。
调用方可传 `refresh=True` 强制刷新。

线程安全：每次调用打开一个独立的 SessionLocal（不复用 self.db_session 是因为
APScheduler/Worker 可能在多线程并发执行；构造时传入的 db_session 主要供测试覆盖）。
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal, models

from ._paths import ensure_scripts_on_path

_log = logging.getLogger(__name__)

_CACHE_TTL = timedelta(days=7)
_TIMEOUT = 30
_SS_BASE = "https://api.semanticscholar.org/graph/v1"
_OPENALEX_BASE = "https://api.openalex.org"
_PER_PAGE = 100  # 双源都按 100 上限拉，避免分页递归（M2.1 单页够用）


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_doi(doi: str) -> str:
    """归一化 DOI：剥 https://doi.org/ 前缀，去空白，转小写。"""
    d = (doi or "").strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.lower().startswith(prefix):
            d = d[len(prefix):]
            break
    return d.lower()


def _ss_headers() -> dict:
    ensure_scripts_on_path()
    try:
        from config import SS_API_KEY  # type: ignore
    except Exception:
        return {}
    return {"x-api-key": SS_API_KEY} if SS_API_KEY else {}


def _openalex_mailto() -> Optional[str]:
    ensure_scripts_on_path()
    try:
        from config import UNPAYWALL_EMAIL  # type: ignore
        return UNPAYWALL_EMAIL or None
    except Exception:
        return None


class ForwardTrackService:
    """前向追踪 service。多线程下使用类方法 + 内部 session，避免共享 ORM 实例。"""

    def __init__(self, db_session: Optional[Session] = None) -> None:
        # db_session 只用于测试注入；生产路径用 SessionLocal 重新开 session
        self.db_session = db_session

    # ─── 主入口 ─────────────────────────────────────────────────────

    def track(self, doi: str, *, refresh: bool = False, limit: int = 100) -> dict:
        """根据 DOI 查"被谁引用"。命中缓存优先返回。

        返回:
          {
            "doi": "...",
            "citing_count": int,
            "citing_papers": [{doi,title,year,authors,source}],
            "cached": bool,
            "fetched_at": isoformat (UTC)
          }
        """
        doi_norm = _normalize_doi(doi)
        if not doi_norm:
            raise ValueError("doi is required")

        session = self.db_session or SessionLocal()
        owns_session = self.db_session is None
        try:
            if not refresh:
                cached = self._read_cache(session, doi_norm)
                if cached is not None:
                    payload = dict(cached.result_json)
                    payload["cached"] = True
                    return payload

            citing = self._merge(self._fetch_ss(doi_norm, limit),
                                 self._fetch_openalex(doi_norm, limit))
            payload = {
                "doi": doi_norm,
                "citing_count": len(citing),
                "citing_papers": citing,
                "fetched_at": _utcnow().isoformat() + "Z",
                "cached": False,
            }
            self._write_cache(session, doi_norm, payload)
            if owns_session:
                session.commit()
            return payload
        except Exception:
            if owns_session:
                session.rollback()
            raise
        finally:
            if owns_session:
                session.close()

    # ─── 缓存 ───────────────────────────────────────────────────────

    def _read_cache(self, session: Session, doi_norm: str) -> Optional[models.ForwardTrackCache]:
        row = session.execute(
            select(models.ForwardTrackCache).where(models.ForwardTrackCache.doi == doi_norm)
        ).scalar_one_or_none()
        if row is None:
            return None
        # 边界：刚好等于 TTL 视为过期重查（"7 天内不重查"的更严格解读）
        if (_utcnow() - row.fetched_at) >= _CACHE_TTL:
            return None
        return row

    def _write_cache(self, session: Session, doi_norm: str, payload: dict) -> None:
        row = session.execute(
            select(models.ForwardTrackCache).where(models.ForwardTrackCache.doi == doi_norm)
        ).scalar_one_or_none()
        if row is None:
            session.add(models.ForwardTrackCache(
                doi=doi_norm,
                result_json=payload,
                fetched_at=_utcnow(),
            ))
            # 并发同 DOI miss 时，flush 会撞 UNIQUE doi —— 回退后改用 UPDATE 路径，
            # 这样调用方仍能拿到一份缓存（最后写入者赢），不让一方报 500。
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                row = session.execute(
                    select(models.ForwardTrackCache)
                    .where(models.ForwardTrackCache.doi == doi_norm)
                ).scalar_one_or_none()
                if row is not None:
                    row.result_json = payload
                    row.fetched_at = _utcnow()
                    session.flush()
        else:
            row.result_json = payload
            row.fetched_at = _utcnow()
            session.flush()

    # ─── 数据源 ─────────────────────────────────────────────────────

    def _fetch_ss(self, doi: str, limit: int) -> list[dict]:
        """SS Citing Papers。失败返回 []，不阻塞另一源。"""
        try:
            url = f"{_SS_BASE}/paper/DOI:{doi}/citations"
            params = {
                "fields": "title,year,authors,externalIds",
                "limit": min(limit, _PER_PAGE),
            }
            resp = httpx.get(url, params=params, headers=_ss_headers(), timeout=_TIMEOUT)
            if resp.status_code != 200:
                _log.warning("[ss] forward-track %s: HTTP %s", doi, resp.status_code)
                return []
            out: list[dict] = []
            for entry in resp.json().get("data", []):
                p = entry.get("citingPaper") or {}
                if not p:
                    continue
                ext = p.get("externalIds") or {}
                out.append({
                    "doi": _normalize_doi(ext.get("DOI", "") or ""),
                    "title": (p.get("title") or "").strip(),
                    "year": p.get("year"),
                    "authors": ", ".join(
                        (a.get("name") or "") for a in (p.get("authors") or [])[:3]
                    ),
                    "source": "ss",
                })
            return out
        except Exception as e:
            _log.warning("[ss] forward-track %s failed: %s", doi, e)
            return []

    def _fetch_openalex(self, doi: str, limit: int) -> list[dict]:
        """OpenAlex cited_by。先 DOI→work id，再 cites filter。"""
        try:
            mailto = _openalex_mailto()
            params = {"mailto": mailto} if mailto else {}
            r1 = httpx.get(f"{_OPENALEX_BASE}/works/doi:{doi}",
                           params=params, timeout=_TIMEOUT)
            if r1.status_code != 200:
                return []
            work_id = (r1.json().get("id") or "").rsplit("/", 1)[-1]
            if not work_id:
                return []

            r2_params = {
                "filter": f"cites:{work_id}",
                "select": "title,doi,publication_year,authorships",
                "per-page": min(limit, _PER_PAGE),
            }
            if mailto:
                r2_params["mailto"] = mailto
            r2 = httpx.get(f"{_OPENALEX_BASE}/works", params=r2_params, timeout=_TIMEOUT)
            if r2.status_code != 200:
                _log.warning("[openalex] forward-track %s: HTTP %s", doi, r2.status_code)
                return []
            out: list[dict] = []
            for w in r2.json().get("results", []):
                out.append({
                    "doi": _normalize_doi((w.get("doi") or "")),
                    "title": (w.get("title") or "").strip(),
                    "year": w.get("publication_year"),
                    "authors": ", ".join(
                        (a.get("author") or {}).get("display_name", "")
                        for a in (w.get("authorships") or [])[:3]
                    ),
                    "source": "openalex",
                })
            return out
        except Exception as e:
            _log.warning("[openalex] forward-track %s failed: %s", doi, e)
            return []

    # ─── 去重合并 ───────────────────────────────────────────────────

    @staticmethod
    def _merge(*lists: Iterable[dict]) -> list[dict]:
        """按 DOI 优先去重，无 DOI 按 (title.lower(), year) 兜底。
        两源都命中时 source 改写为 "both"，字段择优（保留更长 title / 非空 authors）。
        """
        by_doi: dict[str, dict] = {}
        by_titleyear: dict[tuple, dict] = {}
        order: list[dict] = []

        def _merge_into(existing: dict, new: dict) -> None:
            if len(new.get("title") or "") > len(existing.get("title") or ""):
                existing["title"] = new["title"]
            if not existing.get("authors") and new.get("authors"):
                existing["authors"] = new["authors"]
            if existing.get("year") is None and new.get("year") is not None:
                existing["year"] = new["year"]
            if existing.get("source") != new.get("source"):
                existing["source"] = "both"

        for lst in lists:
            for item in lst:
                doi = item.get("doi") or ""
                key_t = ((item.get("title") or "").strip().lower(), item.get("year"))
                if doi:
                    if doi in by_doi:
                        _merge_into(by_doi[doi], item)
                    else:
                        by_doi[doi] = dict(item)
                        order.append(by_doi[doi])
                else:
                    if key_t[0] and key_t in by_titleyear:
                        _merge_into(by_titleyear[key_t], item)
                    elif key_t[0]:
                        by_titleyear[key_t] = dict(item)
                        order.append(by_titleyear[key_t])
                    else:
                        # 既无 DOI 也无 title，丢弃（无信息量）
                        continue
        return order
