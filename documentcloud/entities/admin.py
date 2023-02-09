# Django
from django.contrib import admin
from django.db import transaction

# DocumentCloud
from documentcloud.core.pagination import LargeTablePaginator
from documentcloud.entities.models import Entity


@admin.register(Entity)
class DocumentAdmin(admin.ModelAdmin):
    """Document Admin"""

    list_display = (
        "name",
        "wikidata_id",
        "owner",
        "created_at",
        "updated_at",
        "access",
    )
    list_filter = ("access", "owner", "created_at", "updated_at")
    search_fields = ("title", "localized_names", "wikidata_id", "wikipedia_url", "owner", "description", "created_at", "updated_at")
    show_full_result_count = False
    paginator = LargeTablePaginator
    ordering = ("pk",)
    fields = (
        "name",
        "localized_names",
        "wikidata_id",
        "wikipedia_url",
        "owner",
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
        "description",
        "created_at",
        "updated_at",
    )

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.index_on_commit(field_updates={f: "set" for f in form.changed_data})

    def delete_model(self, request, obj):
        obj.destroy()