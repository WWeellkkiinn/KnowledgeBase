"""Tracking cache models — DOI-keyed, shared across tenants (public knowledge)."""
from __future__ import annotations

from django.db import models


class ForwardTrackCache(models.Model):
    """Cache of 'who cites this DOI' results. No tenant_id — public knowledge."""

    doi = models.CharField(max_length=256, unique=True, db_index=True)
    result_json = models.JSONField()
    fetched_at = models.DateTimeField()

    class Meta:
        verbose_name = "Forward Track Cache"

    def __str__(self) -> str:
        return f"ForwardCache({self.doi})"


class BackwardTrackCache(models.Model):
    """Cache of 'what this DOI cites' results. No tenant_id — public knowledge."""

    doi = models.CharField(max_length=256, unique=True, db_index=True)
    result_json = models.JSONField()
    fetched_at = models.DateTimeField()

    class Meta:
        verbose_name = "Backward Track Cache"

    def __str__(self) -> str:
        return f"BackwardCache({self.doi})"
