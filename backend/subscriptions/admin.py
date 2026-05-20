from django.contrib import admin

from .models import Subscription, SubscriptionResult


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "sub_type", "active", "description", "created_at")
    list_filter = ("tenant", "active", "sub_type")
    search_fields = ("description", "target_ref")
    readonly_fields = ("created_at", "updated_at", "query_refreshed_at", "last_filled_at")


@admin.register(SubscriptionResult)
class SubscriptionResultAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "subscription", "external_id", "fetched_at")
    list_filter = ("tenant",)
    readonly_fields = ("fetched_at",)
