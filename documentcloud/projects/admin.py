# Django
from django.contrib import admin

# Third Party
from reversion.admin import VersionAdmin

# DocumentCloud
from documentcloud.projects.models import Project


@admin.register(Project)
class ProjectAdmin(VersionAdmin):
    """Document Admin"""

    list_display = ("title", "user", "private")
    list_filter = ("private",)
    search_fields = ("title", "user__username")
    date_hierarchy = "created_at"
    fields = (
        "title",
        "slug",
        "user",
        "description",
        "private",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("slug", "user", "created_at", "updated_at")
