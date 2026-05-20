"""Subscription models — tenant-scoped research interest tracking."""
from __future__ import annotations

from django.db import models

from tenants.models import Tenant


class Subscription(models.Model):
    """A tenant's named research interest that drives explore-pool filling."""

    class SubType(models.TextChoices):
        PAPER_CITATIONS = "paper_citations", "Paper Citations"
        AUTHOR_WORKS = "author_works", "Author Works"
        TOPIC_SEARCH = "topic_search", "Topic Search"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="subscriptions")
    sub_type = models.CharField(max_length=32, choices=SubType.choices, default=SubType.TOPIC_SEARCH)
    description = models.TextField(blank=True, default="")
    # list[str] — generated search queries from LLM
    generated_queries = models.JSONField(null=True, blank=True)
    active = models.BooleanField(default=True, db_index=True)
    # paper DOI / author ID / topic keyword depending on sub_type
    target_ref = models.CharField(max_length=512, blank=True, default="")
    query_refreshed_at = models.DateTimeField(null=True, blank=True)
    last_filled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["tenant", "active"]),
        ]

    def __str__(self) -> str:
        return f"[{self.tenant.slug}] {self.description[:60] or self.target_ref}"


class SubscriptionResult(models.Model):
    """One fetched-paper result linked to a subscription run."""

    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="results"
    )
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="subscription_results")
    # raw metadata from OpenAlex / SS (title, doi, abstract, …)
    raw_metadata = models.JSONField(default=dict)
    external_id = models.CharField(max_length=512, blank=True, default="", db_index=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-fetched_at",)
        indexes = [
            models.Index(fields=["tenant", "subscription"]),
        ]
