"""Root URL conf. Each app exposes its own ninja router under /api/<app>/.

The SSE stream is a plain Django view (StreamingHttpResponse) because ninja
expects schema-bound responses; mounting it at /api/progress/stream keeps the
client-facing prefix consistent.
"""
from django.contrib import admin
from django.urls import path, re_path

from core.api import api
from core.views import progress_sse, spa

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/progress/stream", progress_sse, name="progress-sse"),
    path("api/", api.urls),
    # SPA catch-all — must come last; matches everything not handled above.
    re_path(r"^(?P<path>.*)$", spa, name="spa"),
]
