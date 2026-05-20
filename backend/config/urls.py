"""Root URL conf. Each app exposes its own ninja router under /api/<app>/."""
from django.contrib import admin
from django.urls import path

from core.api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]
