"""_track_base.py — ForwardTrackService / BackwardTrackService 共享基类。

两个 service 仅在缓存表、fetch 函数、payload 字段名、边方向上不同，
其余逻辑（TTL、session 管理、缓存读写、图写入）完全对称，提取到此处统一维护。
"""
from __future__ import annotations

import copy
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal, models
from .graph_writer import write_tracking_results
from .reference_fetcher import normalize_doi

_log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class _BaseTrackService:
    """抽象基类，子类须定义以下类属性：
    - _cache_model : ForwardTrackCache 或 BackwardTrackCache
    - _papers_key  : payload 中论文列表的键名
    - _count_key   : payload 中数量的键名
    - _direction   : "forward" 或 "backward"
    以及实现 _fetch(doi, limit) 方法。
    """

    _cache_model: type
    _papers_key: str
    _count_key: str
    _direction: str
    # 8 天而非 7 天：凌晨 2 点 scheduler 会主动刷新所有核心论文 cache，
    # 留 1 天缓冲，避免"凌晨 2 点之前刚 expire → 用户进页面触发 60s 现场拉"。
    _cache_ttl: Optional[timedelta] = timedelta(days=8)  # None = 永不过期

    def __init__(self, db_session: Optional[Session] = None) -> None:
        self.db_session = db_session

    def _fetch(self, doi: str, limit: Optional[int]) -> list:
        raise NotImplementedError

    def track(
        self,
        doi: str,
        *,
        refresh: bool = False,
        limit: Optional[int] = None,
        from_paper_id: Optional[int] = None,
    ) -> dict:
        doi_norm = normalize_doi(doi)
        if not doi_norm:
            raise ValueError("doi is required or invalid")

        session = self.db_session or SessionLocal()
        owns_session = self.db_session is None
        try:
            if not refresh:
                cached = self._read_cache(session, doi_norm)
                if cached is not None:
                    payload = copy.copy(cached.result_json)
                    payload["cached"] = True
                    # cache 命中分支**不再**重写图边：write_tracking_results 只在
                    # 真实拉取新数据时调一次（缓存第一次写入时已写过）；
                    # 用户每次访问详情页都会触发 cache 命中，重复写边浪费 IO 且若
                    # graph_writer 实现不严会产生重复边。
                    return payload

            items = self._fetch(doi_norm, limit)
            payload = {
                "doi": doi_norm,
                self._count_key: len(items),
                self._papers_key: [
                    {
                        "doi": it.doi,
                        "title": it.title,
                        "year": it.year,
                        "authors": it.authors,
                        "abstract": it.abstract,
                        "source": it.source,
                        "venue_name": it.venue_name,
                        "venue_issn": it.venue_issn,
                    }
                    for it in items
                ],
                "fetched_at": _utcnow().isoformat() + "Z",
                "cached": False,
            }
            self._write_cache(session, doi_norm, payload)
            if from_paper_id is not None:
                write_tracking_results(
                    session, from_paper_id,
                    payload[self._papers_key], self._direction,
                )
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

    def _read_cache(self, session: Session, doi_norm: str):
        row = session.execute(
            select(self._cache_model).where(self._cache_model.doi == doi_norm)
        ).scalar_one_or_none()
        if row is None:
            return None
        if self._cache_ttl is not None and (_utcnow() - row.fetched_at) >= self._cache_ttl:
            return None
        return row

    def _write_cache(self, session: Session, doi_norm: str, payload: dict) -> None:
        row = session.execute(
            select(self._cache_model).where(self._cache_model.doi == doi_norm)
        ).scalar_one_or_none()
        if row is None:
            # 把 add + flush 都包进 begin_nested savepoint：之前在 savepoint 外
            # session.add 时若自动 flush（比如 autoflush on read），IntegrityError
            # 会逃出 savepoint 让外层事务进入失败态，无法走 UPDATE 兜底。
            try:
                with session.begin_nested():
                    session.add(self._cache_model(
                        doi=doi_norm, result_json=payload, fetched_at=_utcnow(),
                    ))
                    session.flush()
            except IntegrityError:
                # 并发竞态：另一个请求已插入同一 DOI，改为 UPDATE
                row = session.execute(
                    select(self._cache_model).where(self._cache_model.doi == doi_norm)
                ).scalar_one_or_none()
                if row is not None:
                    row.result_json = payload
                    row.fetched_at = _utcnow()
                    session.flush()
                else:
                    _log.warning("_write_cache: concurrent delete during upsert, cache lost doi=%s", doi_norm)
        else:
            row.result_json = payload
            row.fetched_at = _utcnow()
            session.flush()
