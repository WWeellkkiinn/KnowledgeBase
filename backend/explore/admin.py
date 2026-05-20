from django.contrib import admin

from .models import ExplorePool, TagDict


@admin.register(ExplorePool)
class ExplorePoolAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "subscription", "action", "scored_at", "found_at")
    list_filter = ("tenant", "action")
    search_fields = ("external_id",)
    readonly_fields = ("found_at", "acted_at", "scored_at")


@admin.register(TagDict)
class TagDictAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "tag", "alpha", "beta")
    list_filter = ("tenant",)
    search_fields = ("tag",)
