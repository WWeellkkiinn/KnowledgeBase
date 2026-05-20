"""Email helpers for auth flows."""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

_log = logging.getLogger(__name__)


def _superadmin_emails() -> list[str]:
    from accounts.models import User  # local import avoids circular at module level

    explicit = getattr(settings, "DJANGO_SUPERADMIN_EMAIL", "")
    if explicit:
        return [explicit]
    return list(User.objects.filter(is_superuser=True).values_list("email", flat=True))


def send_pending_approval_notice(user) -> None:
    """Notify super-admins that a new user is waiting for approval."""
    recipients = _superadmin_emails()
    if not recipients:
        _log.warning("[email] No super-admin recipients found for approval notice")
        return
    send_mail(
        subject="[KnowledgeBase] New user pending approval",
        message=(
            f"A new user has registered and is waiting for approval.\n\n"
            f"Email: {user.email}\n"
            f"Note: {user.application_note or '(none)'}\n\n"
            f"Please log into the admin panel to approve or reject this request."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipients,
        fail_silently=True,
    )


def send_magic_link(user, url: str) -> None:
    """Send a magic login link to the user."""
    send_mail(
        subject="[KnowledgeBase] Your login link",
        message=(
            f"Hello,\n\n"
            f"Click the link below to log in. It expires in 15 minutes and can only be used once.\n\n"
            f"{url}\n\n"
            f"If you did not request this, you can ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )
