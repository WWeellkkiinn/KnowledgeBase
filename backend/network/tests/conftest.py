import pytest
from tenants.models import Tenant


@pytest.fixture
def tenant_a(db):
    return Tenant.objects.create(name="Network Tenant A", slug="net-a")


@pytest.fixture
def tenant_b(db):
    return Tenant.objects.create(name="Network Tenant B", slug="net-b")
