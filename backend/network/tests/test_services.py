import pytest
from network.models import Edge
from network.services import get_edges, to_cytoscape


@pytest.mark.django_db
def test_tenant_isolation(tenant_a, tenant_b):
    Edge.objects.create(tenant=tenant_a, from_paper_id=1, to_paper_id=2, direction="backward")
    Edge.objects.create(tenant=tenant_b, from_paper_id=1, to_paper_id=3, direction="backward")

    edges_a = get_edges(tenant_a.id)
    edges_b = get_edges(tenant_b.id)
    assert len(edges_a) == 1
    assert edges_a[0].to_paper_id == 2
    assert len(edges_b) == 1
    assert edges_b[0].to_paper_id == 3


@pytest.mark.django_db
def test_cytoscape_format(tenant_a):
    Edge.objects.create(tenant=tenant_a, from_paper_id=10, to_paper_id=20, direction="forward")
    edges = get_edges(tenant_a.id)
    cy = to_cytoscape(edges)
    assert {"data": {"id": "10"}} in cy["nodes"]
    assert {"data": {"id": "20"}} in cy["nodes"]
    assert cy["edges"][0]["data"]["source"] == "10"
    assert cy["edges"][0]["data"]["target"] == "20"
