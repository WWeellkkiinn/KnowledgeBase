"""Papers API tests: happy path + tenant isolation."""
import pytest
from django.test import Client

from papers.models import Paper


@pytest.mark.django_db
def test_list_papers_empty(authed_client_a):
    resp = authed_client_a.get("/api/papers")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.django_db
def test_get_paper_happy(authed_client_a, tenant_a):
    paper = Paper.objects.create(
        tenant=tenant_a,
        stem="test-paper",
        title="Test Paper",
        status="analyzed",
        source="root",
    )
    resp = authed_client_a.get(f"/api/papers/{paper.pk}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == paper.pk
    assert data["title"] == "Test Paper"


@pytest.mark.django_db
def test_get_paper_not_found(authed_client_a):
    resp = authed_client_a.get("/api/papers/99999")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_tenant_isolation(authed_client_a, authed_client_b, tenant_a, tenant_b):
    """Tenant A's paper must not be visible to tenant B."""
    paper = Paper.objects.create(
        tenant=tenant_a,
        stem="a-paper",
        title="Only for A",
        status="analyzed",
        source="root",
    )
    # Tenant A can see it
    resp_a = authed_client_a.get(f"/api/papers/{paper.pk}")
    assert resp_a.status_code == 200

    # Tenant B cannot see it
    resp_b = authed_client_b.get(f"/api/papers/{paper.pk}")
    assert resp_b.status_code == 404


@pytest.mark.django_db
def test_list_tenant_isolation(authed_client_a, authed_client_b, tenant_a, tenant_b):
    Paper.objects.create(tenant=tenant_a, stem="a-paper", title="A", source="root")
    Paper.objects.create(tenant=tenant_b, stem="b-paper", title="B", source="root")

    resp_a = authed_client_a.get("/api/papers")
    assert resp_a.status_code == 200
    ids_a = [p["id"] for p in resp_a.json()]

    resp_b = authed_client_b.get("/api/papers")
    assert resp_b.status_code == 200
    ids_b = [p["id"] for p in resp_b.json()]

    assert set(ids_a).isdisjoint(set(ids_b))
