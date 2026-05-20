import pytest
from tenants.models import Tenant
from datetime import datetime, timezone


@pytest.fixture
def tenant_a(db):
    return Tenant.objects.create(name="Track Tenant A", slug="track-a")


@pytest.fixture
def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)
