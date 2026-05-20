from django.contrib import admin

from .models import Paper, PaperFile, PaperTag, Tag


@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "title", "status", "source", "year", "added_at")
    list_filter = ("tenant", "status", "source", "is_core")
    search_fields = ("title", "doi", "stem")
    raw_id_fields = ("tenant",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "name")
    list_filter = ("tenant",)


@admin.register(PaperFile)
class PaperFileAdmin(admin.ModelAdmin):
    list_display = ("id", "paper", "file_type", "path")


@admin.register(PaperTag)
class PaperTagAdmin(admin.ModelAdmin):
    list_display = ("id", "paper", "tag")
