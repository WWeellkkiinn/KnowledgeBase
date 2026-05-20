from django.contrib import admin

from .models import Journal


@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display = ("id", "issn", "name", "quality_tier", "is_predatory", "oa_status")
    search_fields = ("name", "issn")
    list_filter = ("quality_tier", "is_predatory", "source_dataset")
