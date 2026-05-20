"""Plain Django views that don't fit the ninja API surface (mainly SSE)."""
from __future__ import annotations

from django.http import HttpRequest, HttpResponseBadRequest, HttpResponseForbidden, StreamingHttpResponse

from .progress import stream as progress_stream


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
