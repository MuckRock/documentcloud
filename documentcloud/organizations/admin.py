# Django
from django.contrib import admin

# Third Party
from squarelet_auth.organizations.admin import OrganizationAdmin as SAOrganizationAdmin

# DocumentCloud
from documentcloud.organizations.models import Organization


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
