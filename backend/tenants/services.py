"""Tenant management services."""
from __future__ import annotations

from accounts.models import Membership, User
from tenants.models import Tenant


def create_tenant(name: str, owner_user: User) -> Tenant:
    """Create a new Tenant and assign owner_user as Owner."""
    tenant = Tenant.objects.create(name=name)
    Membership.objects.create(user=owner_user, tenant=tenant, role=Membership.Role.OWNER)
    return tenant


def add_member(tenant: Tenant, user: User, role: str = Membership.Role.MEMBER) -> Membership:
    """Add user to tenant with given role, or update existing membership role."""
    membership, _ = Membership.objects.update_or_create(
        user=user,
        tenant=tenant,
        defaults={"role": role},
    )
    return membership
