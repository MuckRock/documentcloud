# Django
from django.contrib import admin
from django.db import transaction

# DocumentCloud
from documentcloud.core.pagination import LargeTablePaginator
from documentcloud.documents.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Document Admin"""

    list_display = (
        "title",
        "user",
        "organization",
        "access",
        "status",
        "noindex",
    )
    list_filter = ("access", "status", "language")
    search_fields = ("title", "user__username", "organization__name")
    show_full_result_count = False
    paginator = LargeTablePaginator
    ordering = ("pk",)
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
        "related_article",
        "published_url",
        "created_at",
        "updated_at",
        "page_count",
        "page_spec",
        "solr_dirty",
        "data",
        "noindex",
    )
    readonly_fields = (
        "slug",
        "user",
        "organization",
        "status",
        "created_at",
        "updated_at",
        "page_count",
        "page_spec",
        "solr_dirty",
        "data",
    )

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.index_on_commit(field_updates={f: "set" for f in form.changed_data})

    def delete_model(self, request, obj):
        obj.destroy()
