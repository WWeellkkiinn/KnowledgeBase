import pytest
from tenants.models import Tenant
from subscriptions.models import Subscription


@pytest.fixture
def tenant_a(db):
    return Tenant.objects.create(name="Explore Tenant A", slug="explore-a")


@pytest.fixture
def tenant_b(db):
    return Tenant.objects.create(name="Explore Tenant B", slug="explore-b")


@pytest.fixture
def sub_a(tenant_a):
    return Subscription.objects.create(
        tenant=tenant_a, description="ML", generated_queries=["machine learning", "deep learning"]
    )
