# Django
from django.contrib import admin

# Third Party
from squarelet_auth.organizations.admin import OrganizationAdmin as SAOrganizationAdmin

# DocumentCloud
from documentcloud.organizations.models import AICreditLog, Organization


@admin.register(Organization)
class OrganizationAdmin(SAOrganizationAdmin):
    """Organization Admin"""

    fields = SAOrganizationAdmin.fields + (
        "ai_credits_per_month",
        "monthly_ai_credits",
        "number_ai_credits",
        "language",
        "document_language",
    )
    readonly_fields = SAOrganizationAdmin.readonly_fields + ("ai_credits_per_month",)
    list_select_related = ("entitlement",)


@admin.register(AICreditLog)
class AICreditLogAdmin(admin.ModelAdmin):
    """AI Credit Log Admin"""

    list_display = (
        "organization",
        "user",
        "amount",
        "note",
        "created_at",
    )
    list_select_related = ("user", "organization")
    search_fields = ("organization__name",)
    date_hierarchy = "created_at"
    fields = ("organization", "user", "amount", "note", "created_at")
    readonly_fields = ("organization", "user", "amount", "note", "created_at")
