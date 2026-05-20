"""Celery app. Sub-agents (A/B) define tasks under their own `tasks.py`."""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("kb")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
