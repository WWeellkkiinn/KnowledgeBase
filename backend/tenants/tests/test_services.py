"""Tenant services tests."""
from __future__ import annotations

import pytest

from accounts.models import Membership, User
from tenants.models import Tenant
from tenants.services import add_member, create_tenant


@pytest.mark.django_db
def test_create_tenant_creates_owner_membership(db):
    user = User.objects.create_user(email="owner@test.com", approval_status=User.Approval.APPROVED)
    tenant = create_tenant("My Lab", user)

    assert Tenant.objects.filter(pk=tenant.pk).exists()
    m = Membership.objects.get(user=user, tenant=tenant)
    assert m.role == Membership.Role.OWNER


@pytest.mark.django_db
def test_add_member(db):
    owner = User.objects.create_user(email="owner2@test.com", approval_status=User.Approval.APPROVED)
    member = User.objects.create_user(email="member@test.com", approval_status=User.Approval.APPROVED)
    tenant = create_tenant("Lab 2", owner)

    m = add_member(tenant, member, Membership.Role.MEMBER)
    assert m.role == Membership.Role.MEMBER
    assert Membership.objects.filter(user=member, tenant=tenant).count() == 1


@pytest.mark.django_db
def test_add_member_updates_existing_role(db):
    owner = User.objects.create_user(email="owner3@test.com", approval_status=User.Approval.APPROVED)
    user = User.objects.create_user(email="promote@test.com", approval_status=User.Approval.APPROVED)
    tenant = create_tenant("Lab 3", owner)

    add_member(tenant, user, Membership.Role.MEMBER)
    add_member(tenant, user, Membership.Role.ADMIN)

    m = Membership.objects.get(user=user, tenant=tenant)
    assert m.role == Membership.Role.ADMIN
