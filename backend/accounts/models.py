"""User / Membership / MagicLinkToken.

A User must be approved by a super-admin before they can log in. Membership
ties them to a Tenant with a role. MagicLinkToken stores one-time login codes
(emailed link).
"""
from __future__ import annotations

import secrets
from datetime import timedelta

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone

from tenants.models import Tenant


class UserManager(BaseUserManager):
    """Email is the natural login key; username field is kept for Admin compat."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("Email required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("approval_status", User.Approval.APPROVED)
        if not extra["is_staff"]:
            raise ValueError("Superuser must have is_staff=True")
        if not extra["is_superuser"]:
            raise ValueError("Superuser must have is_superuser=True")
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    class Approval(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    # Make email the unique identifier; keep username nullable for Admin display.
    username = models.CharField(max_length=150, blank=True)
    email = models.EmailField(unique=True)
    approval_status = models.CharField(
        max_length=16, choices=Approval.choices, default=Approval.PENDING
    )
    application_note = models.TextField(blank=True, help_text="Why this user requested access")
    approved_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def is_approved(self) -> bool:
        return self.approval_status == self.Approval.APPROVED


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("user", "tenant"),)


def _gen_token() -> str:
    return secrets.token_urlsafe(32)


class MagicLinkToken(models.Model):
    """One-time email login token. django-sesame handles signed-URL flow,
    this model is for the request/approval audit trail and rate-limiting."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="magic_tokens")
    token = models.CharField(max_length=64, unique=True, default=_gen_token)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def issue(cls, user: User, ttl_seconds: int = 900) -> "MagicLinkToken":
        return cls.objects.create(
            user=user, expires_at=timezone.now() + timedelta(seconds=ttl_seconds)
        )

    def is_valid(self) -> bool:
        return self.used_at is None and self.expires_at > timezone.now()
