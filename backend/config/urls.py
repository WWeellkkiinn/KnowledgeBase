"""Root URL conf. Each app exposes its own ninja router under /api/<app>/.

The SSE stream is a plain Django view (StreamingHttpResponse) because ninja
expects schema-bound responses; mounting it at /api/progress/stream keeps the
client-facing prefix consistent.
"""
from django.contrib import admin
from django.urls import path

from core.api import api
from core.views import progress_sse

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/progress/stream", progress_sse, name="progress-sse"),
    path("api/", api.urls),
]
