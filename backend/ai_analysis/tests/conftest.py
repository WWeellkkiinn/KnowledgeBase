"""Fixtures for ai_analysis tests."""
import pytest
from accounts.models import User
from tenants.models import Tenant


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Test Tenant", slug="test-tenant")


@pytest.fixture
def paper(db, tenant):
    from papers.models import Paper
    return Paper.objects.create(
        tenant=tenant,
        stem="test-paper",
        title="Test Paper",
        abstract="This is a test abstract.",
        source="root",
    )
