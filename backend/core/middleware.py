"""Tenant context + Postgres RLS injection.

`TenantContextMiddleware`:
  1. Resolves the active tenant for the request (single-membership users: their only
     tenant; multi-membership users: from a session key set during login or
     tenant switch).
  2. Attaches `request.tenant` (None for exempt paths / anonymous users).
  3. Sets the Postgres session variable `app.tenant_id` via `SET LOCAL` so any
     RLS policies on business tables auto-filter. Wrapped in an atomic block so
     `SET LOCAL` actually scopes to the request.

Exempt prefixes come from `settings.TENANT_EXEMPT_PATH_PREFIXES`. Those paths
don't get the RLS guard set — they're either admin (uses Django's own auth)
or auth endpoints that operate without a tenant.
"""
from __future__ import annotations

import logging
from typing import Callable

from django.conf import settings
from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse

_log = logging.getLogger(__name__)


def _resolve_tenant(request: HttpRequest):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    # Explicit tenant pin from session (set during login / switch)
    pinned_id = request.session.get("active_tenant_id")
    qs = user.memberships.select_related("tenant").filter(tenant__is_active=True)
    if pinned_id:
        m = qs.filter(tenant_id=pinned_id).first()
        if m:
            return m.tenant
    # Fall back to first membership
    m = qs.first()
    return m.tenant if m else None


class TenantContextMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response
        self.exempt = tuple(getattr(settings, "TENANT_EXEMPT_PATH_PREFIXES", ()))

    def _is_exempt(self, path: str) -> bool:
        return any(path.startswith(prefix) for prefix in self.exempt)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if self._is_exempt(request.path):
            request.tenant = None
            return self.get_response(request)

        tenant = _resolve_tenant(request)
        request.tenant = tenant

        if tenant is None:
            return self.get_response(request)

        # SET LOCAL only applies inside a transaction; wrap the request.
        with transaction.atomic():
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL app.tenant_id = %s", [str(tenant.pk)])
            except Exception as exc:  # pragma: no cover — keep request alive on bad pg state
                _log.warning("[tenant] SET LOCAL failed: %s", exc)
            return self.get_response(request)
