"""Fixtures for papers tests."""
import pytest
from django.test import Client

from accounts.models import User
from tenants.models import Tenant


@pytest.fixture
def tenant_a(db):
    return Tenant.objects.create(name="Tenant A", slug="tenant-a")


@pytest.fixture
def tenant_b(db):
    return Tenant.objects.create(name="Tenant B", slug="tenant-b")


@pytest.fixture
def user_a(db, tenant_a):
    from accounts.models import Membership
    u = User.objects.create_user(email="a@example.com", approval_status="approved")
    Membership.objects.create(user=u, tenant=tenant_a, role="member")
    return u


@pytest.fixture
def user_b(db, tenant_b):
    from accounts.models import Membership
    u = User.objects.create_user(email="b@example.com", approval_status="approved")
    Membership.objects.create(user=u, tenant=tenant_b, role="member")
    return u


@pytest.fixture
def authed_client_a(user_a, tenant_a):
    c = Client()
    c.force_login(user_a)
    session = c.session
    session["active_tenant_id"] = tenant_a.pk
    session.save()
    return c


@pytest.fixture
def authed_client_b(user_b, tenant_b):
    c = Client()
    c.force_login(user_b)
    session = c.session
    session["active_tenant_id"] = tenant_b.pk
    session.save()
    return c
