# Django
from django.contrib import admin

# Third Party
from parler.admin import TranslatableAdmin

# DocumentCloud
from documentcloud.core.pagination import LargeTablePaginator
from documentcloud.entities.models import Entity


@admin.register(Entity)
class EntityAdmin(TranslatableAdmin):
    """Entity Admin"""

    list_display = (
        "name",
        "wikidata_id",
        "user",
        "access",
    )
    list_filter = ("access",)
    search_fields = (
        "translations__name",
        "wikidata_id",
    )
    show_full_result_count = False
    paginator = LargeTablePaginator
    ordering = ("pk",)
    fields = (
        "name",
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
        "wikidata_id",
        "wikipedia_url",
        "user",
        "description",
        "created_at",
        "updated_at",
        "access",
    )
