# Django
from django.contrib import admin

# DocumentCloud
from documentcloud.statistics.models import Statistics


@admin.register(Statistics)
class StatisticsAdmin(admin.ModelAdmin):
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

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.opts.local_fields if field.name != "id"]
