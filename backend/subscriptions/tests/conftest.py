import pytest
from tenants.models import Tenant


@pytest.fixture
def tenant_a(db):
    return Tenant.objects.create(name="Tenant A", slug="tenant-a")


@pytest.fixture
def tenant_b(db):
    return Tenant.objects.create(name="Tenant B", slug="tenant-b")
