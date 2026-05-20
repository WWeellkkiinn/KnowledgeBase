"""Papers domain models."""
from __future__ import annotations

from django.db import models

from tenants.models import Tenant


class Tag(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_index=True)
    name = models.CharField(max_length=32)

    class Meta:
        unique_together = (("tenant", "name"),)
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Paper(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        ANALYZED = "analyzed", "Analyzed"
        FAILED = "failed", "Failed"

    class Source(models.TextChoices):
        ROOT = "root", "Root"
        REF = "ref", "Ref"
        FORWARD = "forward", "Forward"
        SUBSCRIPTION = "subscription", "Subscription"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_index=True)
    stem = models.CharField(max_length=512, db_index=True)
    doi = models.CharField(max_length=256, null=True, blank=True, db_index=True)
    arxiv_id = models.CharField(max_length=64, null=True, blank=True)
    title = models.TextField(null=True, blank=True)
    abstract = models.TextField(null=True, blank=True)
    authors_json = models.JSONField(null=True, blank=True)
    year = models.IntegerField(null=True, blank=True)
    journal = models.ForeignKey(
        "journals.Journal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="papers",
        db_column="journal_id",
    )
    pdf_path = models.CharField(max_length=1024, null=True, blank=True)
    md_path = models.CharField(max_length=1024, null=True, blank=True)
    sha1 = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    refs_path = models.CharField(max_length=1024, null=True, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    failure_reason = models.TextField(null=True, blank=True)
    source = models.CharField(max_length=32, choices=Source.choices, default=Source.REF)
    is_core = models.BooleanField(default=False, db_index=True)
    added_at = models.DateTimeField(auto_now_add=True)
    analyzed_at = models.DateTimeField(null=True, blank=True)
    ai_summary = models.JSONField(null=True, blank=True)
    ai_analyzed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = (("tenant", "stem"),)
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "source"]),
        ]

    def __str__(self) -> str:
        return self.title or self.stem


class PaperFile(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_index=True)
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="files")
    file_type = models.CharField(max_length=16)  # pdf|md|refs
    path = models.CharField(max_length=1024)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("paper", "file_type"),)


class PaperTag(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_index=True)
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="paper_tags")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="paper_tags")

    class Meta:
        unique_together = (("paper", "tag"),)
