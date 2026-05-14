"""_track_base.py — ForwardTrackService / BackwardTrackService 共享基类。

两个 service 仅在缓存表、fetch 函数、payload 字段名、边方向上不同，
其余逻辑（TTL、session 管理、缓存读写、图写入）完全对称，提取到此处统一维护。
"""
from __future__ import annotations

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
_CACHE_TTL = timedelta(days=7)


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

    def __init__(self, db_session: Optional[Session] = None) -> None:
        self.db_session = db_session

    def _fetch(self, doi: str, limit: int) -> list:
        raise NotImplementedError

    def track(
        self,
        doi: str,
        *,
        refresh: bool = False,
        limit: int = 100,
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
                    payload = dict(cached.result_json)
                    payload["cached"] = True
                    if from_paper_id is not None:
                        write_tracking_results(
                            session, from_paper_id,
                            payload[self._papers_key], self._direction,
                        )
                        if owns_session:
                            session.commit()
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
        if (_utcnow() - row.fetched_at) >= _CACHE_TTL:
            return None
        return row

    def _write_cache(self, session: Session, doi_norm: str, payload: dict) -> None:
        row = session.execute(
            select(self._cache_model).where(self._cache_model.doi == doi_norm)
        ).scalar_one_or_none()
        if row is None:
            session.add(self._cache_model(
                doi=doi_norm, result_json=payload, fetched_at=_utcnow(),
            ))
            try:
                with session.begin_nested():
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
            row.result_json = payload
            row.fetched_at = _utcnow()
            session.flush()
