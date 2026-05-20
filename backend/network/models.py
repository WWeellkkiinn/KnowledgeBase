"""Network models — citation edges between papers, scoped to tenant."""
from __future__ import annotations

from django.db import models

from tenants.models import Tenant


class Edge(models.Model):
    """A directed citation edge from_paper → to_paper within a tenant's graph."""

    class Direction(models.TextChoices):
        FORWARD = "forward", "Forward"   # to_paper cites from_paper
        BACKWARD = "backward", "Backward"  # from_paper cites to_paper

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="edges")
    # IDs reference papers.Paper (owned by Agent A); stored as int to avoid cross-app FK
    from_paper_id = models.IntegerField(db_index=True)
    to_paper_id = models.IntegerField(db_index=True)
    direction = models.CharField(max_length=16, choices=Direction.choices)
    ref_index = models.IntegerField(null=True, blank=True)
    ref_title = models.TextField(blank=True, default="")
    discovered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "from_paper_id"]),
            models.Index(fields=["tenant", "to_paper_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "from_paper_id", "to_paper_id", "direction"],
                name="uq_edge_tenant_from_to_dir",
            )
        ]

    def __str__(self) -> str:
        return f"Edge({self.from_paper_id}→{self.to_paper_id} [{self.direction}])"
