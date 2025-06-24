# Django
from django.contrib import admin
from django.http import HttpResponse

# Standard Library
import csv

# DocumentCloud
from documentcloud.statistics.models import Statistics


@admin.register(Statistics)
class StatisticsAdmin(admin.ModelAdmin):

    def export_statistics_as_csv(self, request, queryset):
        """Export selected DocumentCloud statistics to CSV."""
        field_names = [
            "date",
            "total_documents",
            "total_documents_public",
            "total_documents_private",
            "total_documents_organization",
            "total_pages",
            "total_notes",
            "total_projects",
        ]

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            "attachment; filename=documentcloud_statistics.csv"
        )

        writer = csv.writer(response)
        writer.writerow(field_names)

        for stat in queryset:
            writer.writerow(
                [
                    stat.date.isoformat(),
                    stat.total_documents,
                    stat.total_documents_public,
                    stat.total_documents_private,
                    stat.total_documents_organization,
                    stat.total_pages,
                    stat.total_notes,
                    stat.total_projects,
                ]
            )

        return response

    export_statistics_as_csv.short_description = "Export selected statistics to CSV"

    list_display = (
        "date",
        "total_documents",
        "total_documents_public",
        "total_documents_private",
        "total_documents_organization",
        "total_pages",
        "total_notes",
        "total_projects",
    )

    actions = [export_statistics_as_csv]

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.opts.local_fields if field.name != "id"]
