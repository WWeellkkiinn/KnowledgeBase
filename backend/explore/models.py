"""ExplorePool — per-tenant candidate papers awaiting bandit scoring and user action."""
from __future__ import annotations

from django.db import models

from tenants.models import Tenant
from subscriptions.models import Subscription


class ExplorePool(models.Model):
    """A candidate paper surface in the explore feed for a tenant."""

    class Action(models.TextChoices):
        SAVED = "saved", "Saved"
        SKIPPED = "skipped", "Skipped"
        PASSED = "passed", "Passed"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="explore_pool")
    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="explore_pool"
    )
    # FK to papers app (Agent A owns papers.Paper); stored as int to avoid cross-app model import
    paper_id = models.IntegerField(null=True, blank=True, db_index=True)

    external_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    raw_metadata_json = models.JSONField(null=True, blank=True)

    # LLM scoring output
    title_zh = models.TextField(blank=True, default="")
    tags_json = models.JSONField(null=True, blank=True)
    research_question = models.TextField(blank=True, default="")
    methodology = models.TextField(blank=True, default="")
    key_findings_json = models.JSONField(null=True, blank=True)
    llm_reason = models.TextField(blank=True, default="")
    scored_at = models.DateTimeField(null=True, blank=True)
    score_attempts = models.IntegerField(default=0)

    action = models.CharField(
        max_length=16, choices=Action.choices, null=True, blank=True, db_index=True
    )
    acted_at = models.DateTimeField(null=True, blank=True)
    found_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-found_at",)
        indexes = [
            models.Index(fields=["tenant", "subscription", "action"]),
            models.Index(fields=["tenant", "scored_at"]),
        ]
        unique_together = (("subscription", "external_id"),)

    def __str__(self) -> str:
        meta = self.raw_metadata_json or {}
        return meta.get("title", f"ExplorePool#{self.pk}")[:80]


class TagDict(models.Model):
    """Per-tenant bandit arm — Beta distribution (alpha, beta) per tag."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="tag_dict")
    tag = models.CharField(max_length=32, db_index=True)
    source = models.CharField(max_length=16, default="llm")
    alpha = models.FloatField(default=0.5)
    beta = models.FloatField(default=0.5)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("tenant", "tag"),)
