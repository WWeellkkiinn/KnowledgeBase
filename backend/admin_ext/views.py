"""Custom admin views for user approval workflow."""
from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.urls import path
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from accounts.models import Membership, User
from tenants.models import Tenant
from tenants.services import add_member


class ApprovalForm(forms.Form):
    action = forms.ChoiceField(choices=[("approve", "Approve"), ("reject", "Reject")])
    tenant = forms.ModelChoiceField(
        queryset=Tenant.objects.filter(is_active=True),
        required=False,
        help_text="Required when approving",
    )
    role = forms.ChoiceField(choices=Membership.Role.choices, initial=Membership.Role.MEMBER)


@method_decorator(staff_member_required, name="dispatch")
class PendingUsersView(View):
    template_name = "admin_ext/pending_users.html"

    def get(self, request):
        pending = User.objects.filter(approval_status=User.Approval.PENDING).order_by("date_joined")
        tenants = Tenant.objects.filter(is_active=True)
        ctx = {
            **admin.site.each_context(request),
            "pending_users": pending,
            "tenants": tenants,
            "role_choices": Membership.Role.choices,
            "title": "Pending User Approvals",
        }
        return render(request, self.template_name, ctx)

    def post(self, request):
        user_id = request.POST.get("user_id")
        action = request.POST.get("action")
        tenant_id = request.POST.get("tenant")
        role = request.POST.get("role", Membership.Role.MEMBER)

        try:
            user = User.objects.get(pk=user_id, approval_status=User.Approval.PENDING)
        except User.DoesNotExist:
            messages.error(request, "User not found or already processed.")
            return redirect("admin:pending_users")

        if action == "approve":
            if not tenant_id:
                messages.error(request, "Select a tenant before approving.")
                return redirect("admin:pending_users")
            try:
                tenant = Tenant.objects.get(pk=tenant_id, is_active=True)
            except Tenant.DoesNotExist:
                messages.error(request, "Invalid tenant.")
                return redirect("admin:pending_users")

            user.approval_status = User.Approval.APPROVED
            user.approved_at = timezone.now()
            user.save(update_fields=["approval_status", "approved_at"])
            add_member(tenant, user, role)
            messages.success(request, f"Approved {user.email} and added to {tenant.name}.")

        elif action == "reject":
            user.approval_status = User.Approval.REJECTED
            user.save(update_fields=["approval_status"])
            messages.success(request, f"Rejected {user.email}.")

        return redirect("admin:pending_users")


def get_urls():
    return [
        path(
            "pending-users/",
            PendingUsersView.as_view(),
            name="pending_users",
        ),
    ]
