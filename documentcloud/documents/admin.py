# Django
from django.contrib import admin

# Third Party
from reversion.admin import VersionAdmin

# DocumentCloud
from documentcloud.documents.models import Document


@admin.register(Document)
class DocumentAdmin(VersionAdmin):
    """Document Admin"""

    list_display = ("title", "user", "organization", "access", "status")
    list_filter = ("access", "status", "language")
    search_fields = ("title", "user__username", "organization__name")
    date_hierarchy = "created_at"
    fields = (
        "title",
        "slug",
        "user",
        "organization",
        "access",
        "status",
        "language",
        "source",
        "description",
        "created_at",
        "updated_at",
    )
    readonly_fields = (
        "slug",
        "user",
        "organization",
        "status",
        "created_at",
        "updated_at",
    )
