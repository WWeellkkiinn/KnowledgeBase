from django.contrib import admin
from django.utils import timezone

from .models import MagicLinkToken, Membership, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "approval_status", "is_staff", "date_joined", "approved_at")
    list_filter = ("approval_status", "is_staff", "is_superuser")
    search_fields = ("email", "username")
    actions = ("approve_users", "reject_users")
    readonly_fields = ("date_joined", "last_login", "approved_at")

    @admin.action(description="Approve selected users")
    def approve_users(self, request, queryset):
        queryset.update(approval_status=User.Approval.APPROVED, approved_at=timezone.now())

    @admin.action(description="Reject selected users")
    def reject_users(self, request, queryset):
        queryset.update(approval_status=User.Approval.REJECTED)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "created_at")
    list_filter = ("role", "tenant")
    search_fields = ("user__email", "tenant__name")


@admin.register(MagicLinkToken)
class MagicLinkTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "expires_at", "used_at")
    readonly_fields = ("token", "created_at", "expires_at", "used_at")
