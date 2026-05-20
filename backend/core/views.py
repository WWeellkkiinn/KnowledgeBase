"""Plain Django views that don't fit the ninja API surface (SSE, SPA static)."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import (
    FileResponse,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseNotFound,
    StreamingHttpResponse,
)

from .progress import stream as progress_stream

_DIST_DIR = Path("/srv/kb_frontend_dist")


def progress_sse(request: HttpRequest) -> StreamingHttpResponse:
    """Server-Sent Events stream for one task_id.

    Auth: session cookie (handled by AuthenticationMiddleware). Tenant scope is
    not strictly enforced here because task_id is opaque random; if a client
    knows another tenant's task_id they can subscribe, but they can't enumerate
    it. For now: require authenticated user; tighten later if needed.
    """
    if not request.user.is_authenticated:
        return HttpResponseForbidden("login required")
    task_id = request.GET.get("task_id", "").strip()
    if not task_id or len(task_id) > 128:
        return HttpResponseBadRequest("task_id required")

    response = StreamingHttpResponse(
        progress_stream(task_id),
        content_type="text/event-stream",
    )
    # Disable nginx/buffering so events ship immediately.
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def spa(request: HttpRequest, path: str = "") -> HttpResponse:
    """Serve the Vue SPA. Hashed asset files keep a year of cache; everything
    else falls back to index.html for the client-side router."""
    if not _DIST_DIR.is_dir():
        return HttpResponseNotFound(
            "frontend not built; ensure backend/Dockerfile stage 1 ran."
        )
    # Path-traversal hardening
    if path:
        candidate = (_DIST_DIR / path).resolve()
        try:
            candidate.relative_to(_DIST_DIR.resolve())
        except ValueError:
            return HttpResponseNotFound("not found")
        if candidate.is_file():
            ctype, _ = mimetypes.guess_type(str(candidate))
            resp = FileResponse(candidate.open("rb"), content_type=ctype or "application/octet-stream")
            if path.startswith("assets/"):
                resp["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                resp["Cache-Control"] = "no-cache"
            return resp
    # Fallthrough → index.html
    index = _DIST_DIR / "index.html"
    if not index.is_file():
        return HttpResponseNotFound("index.html missing from dist")
    resp = FileResponse(index.open("rb"), content_type="text/html")
    resp["Cache-Control"] = "no-cache"
    return resp
