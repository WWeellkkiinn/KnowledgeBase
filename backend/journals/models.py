"""Journal model with EasyScholar JSON cache."""
from __future__ import annotations

from datetime import datetime

from django.db import models


class Journal(models.Model):
    issn = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=512)
    publisher = models.CharField(max_length=256, null=True, blank=True)
    quality_tier = models.IntegerField(null=True, blank=True)  # 1-4
    is_predatory = models.BooleanField(default=False)
    oa_status = models.CharField(max_length=32, null=True, blank=True)
    source_dataset = models.CharField(max_length=64, null=True, blank=True)
    refreshed_at = models.DateTimeField(null=True, blank=True)
    easyscholar_json = models.JSONField(null=True, blank=True)
    easyscholar_fetched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name
