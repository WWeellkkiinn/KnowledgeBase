"""Magic link issuance and consumption."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login
from django.utils import timezone

_log = logging.getLogger(__name__)

_RATE_LIMIT_SECONDS = 60


def issue(user) -> str:
    """Return a full magic-link URL and create an audit MagicLinkToken.

    Raises ValueError if rate-limited (issued within last 60 s).
    """
    from accounts.models import MagicLinkToken
    from core.email import send_magic_link

    # Rate-limit: one token per email per 60 s
    cutoff = timezone.now() - timedelta(seconds=_RATE_LIMIT_SECONDS)
    if MagicLinkToken.objects.filter(user=user, created_at__gte=cutoff).exists():
        raise ValueError("rate_limited")

    # Build sesame signed query-string
    import sesame.utils as sesame_utils

    qs = sesame_utils.get_query_string(user)  # returns "?sesame=<token>"

    base = getattr(settings, "MAGIC_LINK_BASE_URL", "http://localhost:8000")
    url = f"{base}/api/auth/magic/consume{qs}"

    # Audit record
    MagicLinkToken.issue(user)

    send_magic_link(user, url)
    return url


def consume(request, sesame_token: str):
    """Authenticate via sesame token; mark the latest unused MagicLinkToken.

    Returns the User on success, None on failure.
    """
    from accounts.models import MagicLinkToken, User

    # sesame backend expects the full query-string key in request.GET
    # Caller sets request.GET already (NinjaAPI passes it through).
    from sesame.backends import ModelBackend as SesameBackend

    backend = SesameBackend()
    user = backend.authenticate(request, url_auth_token=sesame_token)
    if user is None:
        return None

    login(request, user, backend="sesame.backends.ModelBackend")

    # Mark the latest valid token as used
    token_obj = (
        MagicLinkToken.objects.filter(user=user, used_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if token_obj and token_obj.is_valid():
        token_obj.used_at = timezone.now()
        token_obj.save(update_fields=["used_at"])

    return user
