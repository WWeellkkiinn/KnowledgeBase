from django.contrib import admin

from .models import BackwardTrackCache, ForwardTrackCache


@admin.register(ForwardTrackCache)
class ForwardTrackCacheAdmin(admin.ModelAdmin):
    list_display = ("doi", "fetched_at")
    search_fields = ("doi",)
    readonly_fields = ("fetched_at",)


@admin.register(BackwardTrackCache)
class BackwardTrackCacheAdmin(admin.ModelAdmin):
    list_display = ("doi", "fetched_at")
    search_fields = ("doi",)
    readonly_fields = ("fetched_at",)
