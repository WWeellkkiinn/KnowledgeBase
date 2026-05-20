from django.contrib import admin

from .models import Edge


@admin.register(Edge)
class EdgeAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "from_paper_id", "to_paper_id", "direction", "discovered_at")
    list_filter = ("tenant", "direction")
    readonly_fields = ("discovered_at",)
