# Django
from django.contrib import admin
from django.http import HttpResponse

# Standard Library
import csv

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

    def export_ai_credit_logs(self, request, queryset):
        """Export selected AI credit logs as CSV."""
        field_names = ["organization", "user", "amount", "note", "created_at"]

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=ai_credit_logs.csv"

        writer = csv.writer(response)
        writer.writerow(field_names)

        for log in queryset:
            writer.writerow(
                [
                    str(log.organization),
                    str(log.user),
                    log.amount,
                    log.note,
                    log.created_at.isoformat(),
                ]
            )

        return response

    export_ai_credit_logs.short_description = "Export selected AI credit logs to CSV"
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
    actions = [export_ai_credit_logs]
