"""_BaseTrackService — shared logic for ForwardTrackService and BackwardTrackService.

Ported from services/_track_base.py; uses Django ORM for cache reads/writes
instead of SQLAlchemy sessions.
"""
from __future__ import annotations

import copy
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from .fetcher import normalize_doi

_log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class _BaseTrackService:
    """Subclasses must define:
    - _cache_model_name : str  Django app_label.ModelName
    - _papers_key       : str
    - _count_key        : str
    - _direction        : str
    and implement _fetch(doi, limit).
    """

    _cache_model_name: str
    _papers_key: str
    _count_key: str
    _direction: str
    _cache_ttl: Optional[timedelta] = timedelta(days=8)

    def _get_cache_model(self):
        from django.apps import apps
        app_label, model_name = self._cache_model_name.split(".")
        return apps.get_model(app_label, model_name)

    def _fetch(self, doi: str, limit: Optional[int]) -> list:
        raise NotImplementedError

    def track(
        self,
        doi: str,
        *,
        refresh: bool = False,
        limit: Optional[int] = None,
        from_paper_id: Optional[int] = None,
        tenant_id: Optional[int] = None,
    ) -> dict:
        doi_norm = normalize_doi(doi)
        if not doi_norm:
            raise ValueError("doi is required or invalid")

        if not refresh:
            cached = self._read_cache(doi_norm)
            if cached is not None:
                payload = copy.copy(cached.result_json)
                payload["cached"] = True
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
        self._write_cache(doi_norm, payload)

        if from_paper_id is not None and tenant_id is not None:
            from network.graph import write_tracking_results
            write_tracking_results(tenant_id, from_paper_id, payload[self._papers_key], self._direction)

        return payload

    def _read_cache(self, doi_norm: str):
        Model = self._get_cache_model()
        try:
            row = Model.objects.get(doi=doi_norm)
        except Model.DoesNotExist:
            return None
        if self._cache_ttl is not None and (_utcnow() - row.fetched_at.replace(tzinfo=None)) >= self._cache_ttl:
            return None
        return row

    def _write_cache(self, doi_norm: str, payload: dict) -> None:
        Model = self._get_cache_model()
        Model.objects.update_or_create(
            doi=doi_norm,
            defaults={"result_json": payload, "fetched_at": _utcnow()},
        )
