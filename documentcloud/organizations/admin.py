# Django
from django.contrib import admin

# Third Party
from reversion.admin import VersionAdmin
from squarelet_auth.organizations.admin import OrganizationAdmin as SAOrganizationAdmin

# DocumentCloud
from documentcloud.organizations.models import Organization


@admin.register(Organization)
class OrganizationAdmin(VersionAdmin, SAOrganizationAdmin):
    """Organization Admin"""

    fields = SAOrganizationAdmin.fields + (
        "pages_per_month",
        "monthly_pages",
        "number_pages",
        "language",
        "document_language",
    )
    readonly_fields = SAOrganizationAdmin.readonly_fields + ("pages_per_month",)
    list_select_related = ("entitlement",)
