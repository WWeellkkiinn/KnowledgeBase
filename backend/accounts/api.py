"""Auth API router — mounted at /api/auth/ by core/api.py."""
from __future__ import annotations

from typing import Optional

from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

router = Router()


# ── Schemas ──────────────────────────────────────────────────────────

class RegisterIn(Schema):
    email: str
    password: Optional[str] = None
    application_note: str = ""


class RegisterOut(Schema):
    status: str
    message: str


class LoginIn(Schema):
    email: str
    password: str


class TenantInfo(Schema):
    id: int
    name: str
    slug: str
    role: str


class MeOut(Schema):
    id: int
    email: str
    approval_status: str
    tenants: list[TenantInfo]
    active_tenant_id: Optional[int]


class MagicLinkIn(Schema):
    email: str


class SwitchTenantIn(Schema):
    tenant_id: int


# ── Helpers ──────────────────────────────────────────────────────────

def _me_payload(request) -> MeOut:
    user = request.user
    memberships = user.memberships.select_related("tenant").filter(tenant__is_active=True)
    return MeOut(
        id=user.pk,
        email=user.email,
        approval_status=user.approval_status,
        tenants=[
            TenantInfo(id=m.tenant.pk, name=m.tenant.name, slug=m.tenant.slug, role=m.role)
            for m in memberships
        ],
        active_tenant_id=request.session.get("active_tenant_id"),
    )


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/register", response=RegisterOut, auth=None)
def register(request, payload: RegisterIn):
    from accounts.models import User
    from core.email import send_pending_approval_notice

    if User.objects.filter(email=payload.email).exists():
        raise HttpError(400, "Email already registered")

    user = User.objects.create_user(
        email=payload.email,
        password=payload.password or None,
        application_note=payload.application_note,
        approval_status=User.Approval.PENDING,
    )
    send_pending_approval_notice(user)
    return RegisterOut(
        status="pending",
        message="Your application has been submitted. You will be notified once approved.",
    )


@router.post("/login", auth=None)
def login_view(request, payload: LoginIn):
    from accounts.models import User

    user = authenticate(request, email=payload.email, password=payload.password)
    if user is None:
        raise HttpError(401, "Invalid credentials")

    if user.approval_status == User.Approval.PENDING:
        raise HttpError(403, "pending_approval")
    if user.approval_status == User.Approval.REJECTED:
        raise HttpError(403, "rejected")

    login(request, user)
    return _me_payload(request)


@router.post("/magic-link", auth=None)
def request_magic_link(request, payload: MagicLinkIn):
    from accounts.models import User
    from accounts.services import magic_link as ml

    try:
        user = User.objects.get(email=payload.email)
    except User.DoesNotExist:
        # Anti-enumeration: always return success
        return {"status": "sent"}

    if not user.is_approved():
        return {"status": "sent"}

    try:
        ml.issue(user)
    except ValueError:
        # rate-limited — still return 200 to avoid enumeration
        pass

    return {"status": "sent"}


@router.get("/magic/consume", auth=None)
def consume_magic_link(request, sesame: str):
    from accounts.services import magic_link as ml

    user = ml.consume(request, sesame)
    if user is None:
        raise HttpError(401, "Invalid or expired token")

    return _me_payload(request)


@router.get("/me")
def me(request):
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
    return _me_payload(request)


@router.post("/switch-tenant")
def switch_tenant(request, payload: SwitchTenantIn):
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")

    has_membership = request.user.memberships.filter(
        tenant_id=payload.tenant_id, tenant__is_active=True
    ).exists()
    if not has_membership:
        raise HttpError(403, "Not a member of this tenant")

    request.session["active_tenant_id"] = payload.tenant_id
    return _me_payload(request)


@router.post("/logout")
def logout_view(request):
    logout(request)
    return {"status": "ok"}
