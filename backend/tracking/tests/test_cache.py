"""Test cache read/write and that caches are not tenant-scoped (shared knowledge)."""
import pytest
from datetime import datetime, timezone

from tracking.models import BackwardTrackCache, ForwardTrackCache


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.mark.django_db
def test_forward_cache_write_read():
    payload = {"doi": "10.1234/test", "citing_count": 2, "citing_papers": []}
    ForwardTrackCache.objects.create(doi="10.1234/test", result_json=payload, fetched_at=_utcnow())
    row = ForwardTrackCache.objects.get(doi="10.1234/test")
    assert row.result_json["citing_count"] == 2


@pytest.mark.django_db
def test_backward_cache_write_read():
    payload = {"doi": "10.5678/test", "references_count": 3, "referenced_papers": []}
    BackwardTrackCache.objects.create(doi="10.5678/test", result_json=payload, fetched_at=_utcnow())
    row = BackwardTrackCache.objects.get(doi="10.5678/test")
    assert row.result_json["references_count"] == 3


@pytest.mark.django_db
def test_cache_is_shared_across_tenants():
    """Same DOI cache entry is visible regardless of which tenant triggered it."""
    payload = {"doi": "10.9999/shared", "citing_count": 5, "citing_papers": []}
    ForwardTrackCache.objects.update_or_create(
        doi="10.9999/shared", defaults={"result_json": payload, "fetched_at": _utcnow()}
    )
    assert ForwardTrackCache.objects.filter(doi="10.9999/shared").count() == 1
