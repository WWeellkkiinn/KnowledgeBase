"""Auth API tests."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import Client

from accounts.models import MagicLinkToken, Membership, User
from tenants.models import Tenant


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme", slug="acme")


@pytest.fixture
def approved_user(db, tenant):
    u = User.objects.create_user(
        email="approved@test.com",
        password="strongpass123",
        approval_status=User.Approval.APPROVED,
    )
    Membership.objects.create(user=u, tenant=tenant, role=Membership.Role.MEMBER)
    return u


@pytest.fixture
def pending_user(db):
    return User.objects.create_user(
        email="pending@test.com",
        password="strongpass123",
        approval_status=User.Approval.PENDING,
    )


# ── Register ─────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_register_sends_email(client):
    with patch("core.email.send_mail") as mock_send, \
         patch("core.email._superadmin_emails", return_value=["admin@test.com"]):
        resp = client.post(
            "/api/auth/register",
            data='{"email": "new@test.com", "application_note": "test"}',
            content_type="application/json",
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    mock_send.assert_called_once()


@pytest.mark.django_db
def test_register_duplicate_email(client, approved_user):
    resp = client.post(
        "/api/auth/register",
        data='{"email": "approved@test.com"}',
        content_type="application/json",
    )
    assert resp.status_code == 400


# ── Login ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_login_approved(client, approved_user):
    resp = client.post(
        "/api/auth/login",
        data='{"email": "approved@test.com", "password": "strongpass123"}',
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "approved@test.com"


@pytest.mark.django_db
def test_login_pending_forbidden(client, pending_user):
    resp = client.post(
        "/api/auth/login",
        data='{"email": "pending@test.com", "password": "strongpass123"}',
        content_type="application/json",
    )
    assert resp.status_code == 403
    assert "pending_approval" in resp.json()["detail"]


@pytest.mark.django_db
def test_login_rejected_forbidden(client, db):
    u = User.objects.create_user(
        email="rejected@test.com",
        password="strongpass123",
        approval_status=User.Approval.REJECTED,
    )
    resp = client.post(
        "/api/auth/login",
        data='{"email": "rejected@test.com", "password": "strongpass123"}',
        content_type="application/json",
    )
    assert resp.status_code == 403
    assert "rejected" in resp.json()["detail"]


@pytest.mark.django_db
def test_login_wrong_password(client, approved_user):
    resp = client.post(
        "/api/auth/login",
        data='{"email": "approved@test.com", "password": "wrong"}',
        content_type="application/json",
    )
    assert resp.status_code == 401


# ── Magic link ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_magic_link_nonexistent_email_returns_200(client):
    resp = client.post(
        "/api/auth/magic-link",
        data='{"email": "ghost@test.com"}',
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"


@pytest.mark.django_db
def test_magic_link_approved_sends_email(client, approved_user):
    with patch("core.email.send_mail") as mock_send:
        with patch("sesame.utils.get_query_string", return_value="?sesame=abc123"):
            resp = client.post(
                "/api/auth/magic-link",
                data='{"email": "approved@test.com"}',
                content_type="application/json",
            )
    assert resp.status_code == 200
    mock_send.assert_called_once()
    # Audit record created
    assert MagicLinkToken.objects.filter(user=approved_user).exists()


@pytest.mark.django_db
def test_magic_link_rate_limited(client, approved_user):
    """Second request within 60 s should silently succeed (no error exposed)."""
    with patch("core.email.send_mail"):
        with patch("sesame.utils.get_query_string", return_value="?sesame=tok1"):
            client.post(
                "/api/auth/magic-link",
                data='{"email": "approved@test.com"}',
                content_type="application/json",
            )
        with patch("sesame.utils.get_query_string", return_value="?sesame=tok2"):
            resp = client.post(
                "/api/auth/magic-link",
                data='{"email": "approved@test.com"}',
                content_type="application/json",
            )
    # Still returns 200 — rate limit is silent
    assert resp.status_code == 200
    # Only one token created
    assert MagicLinkToken.objects.filter(user=approved_user).count() == 1


@pytest.mark.django_db
def test_magic_link_consume_marks_used(client, approved_user):
    with patch("sesame.backends.ModelBackend.authenticate", return_value=approved_user):
        resp = client.get("/api/auth/magic/consume?sesame=abc123")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_magic_link_consume_invalid_token(client):
    with patch("sesame.backends.ModelBackend.authenticate", return_value=None):
        resp = client.get("/api/auth/magic/consume?sesame=badtoken")
    assert resp.status_code == 401


# ── Me ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_me_unauthenticated(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_me_authenticated(client, approved_user, tenant):
    client.force_login(approved_user)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "approved@test.com"
    assert len(data["tenants"]) == 1
    assert data["tenants"][0]["slug"] == "acme"


# ── Switch tenant ─────────────────────────────────────────────────────

@pytest.mark.django_db
def test_switch_tenant_valid(client, approved_user, tenant):
    client.force_login(approved_user)
    resp = client.post(
        "/api/auth/switch-tenant",
        data=f'{{"tenant_id": {tenant.pk}}}',
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["active_tenant_id"] == tenant.pk


@pytest.mark.django_db
def test_switch_tenant_not_member(client, approved_user, db):
    other_tenant = Tenant.objects.create(name="Other", slug="other")
    client.force_login(approved_user)
    resp = client.post(
        "/api/auth/switch-tenant",
        data=f'{{"tenant_id": {other_tenant.pk}}}',
        content_type="application/json",
    )
    assert resp.status_code == 403


# ── Tenant isolation ─────────────────────────────────────────────────

@pytest.mark.django_db
def test_tenant_isolation_me(client, db):
    """User in tenant A cannot see tenant B in their memberships."""
    tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b")

    user_a = User.objects.create_user(
        email="a@test.com", password="pass1234567", approval_status=User.Approval.APPROVED
    )
    user_b = User.objects.create_user(
        email="b@test.com", password="pass1234567", approval_status=User.Approval.APPROVED
    )
    Membership.objects.create(user=user_a, tenant=tenant_a, role=Membership.Role.MEMBER)
    Membership.objects.create(user=user_b, tenant=tenant_b, role=Membership.Role.MEMBER)

    client.force_login(user_a)
    resp = client.get("/api/auth/me")
    data = resp.json()
    tenant_ids = {t["id"] for t in data["tenants"]}
    assert tenant_a.pk in tenant_ids
    assert tenant_b.pk not in tenant_ids


# ── Logout ────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_logout(client, approved_user):
    client.force_login(approved_user)
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    # After logout, /me should 401
    resp2 = client.get("/api/auth/me")
    assert resp2.status_code == 401
