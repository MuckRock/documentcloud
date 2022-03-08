# Django
from django.contrib import admin

# DocumentCloud
from documentcloud.projects.models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
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
