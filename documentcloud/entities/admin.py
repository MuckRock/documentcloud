# Django
from django.contrib import admin

# DocumentCloud
from documentcloud.core.pagination import LargeTablePaginator
from documentcloud.entities.models import Entity


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    """Entity Admin"""

    list_display = (
        "name",
        "wikidata_id",
        "user",
        "created_at",
        "updated_at",
        "access",
    )
    list_filter = ("access",)
    search_fields = (
        "name",
        "wikidata_id",
        "description",
    )
    show_full_result_count = False
    paginator = LargeTablePaginator
    ordering = ("pk",)
    fields = (
        "name",
        "localized_names",
        "wikidata_id",
        "wikipedia_url",
        "user",
        "description",
        "created_at",
        "updated_at",
        "access",
    )
    readonly_fields = (
        "name",
        "localized_names",
        "wikidata_id",
        "wikipedia_url",
        "user",
        "description",
        "created_at",
        "updated_at",
        "access",
    )
