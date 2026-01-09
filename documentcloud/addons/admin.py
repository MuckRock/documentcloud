# Django
from django.conf import settings
from django.contrib import admin, messages
from django.db.models import JSONField, Q
from django.forms import widgets
from django.http import HttpResponse
from django.http.response import HttpResponseRedirect
from django.urls import path, reverse

# Standard Library
import csv
import json

# DocumentCloud
from documentcloud.addons.models import (
    AddOn,
    AddOnDisableLog,
    AddOnEvent,
    AddOnRun,
    GitHubAccount,
    GitHubInstallation,
    VisualAddOn,
)
from documentcloud.addons.tasks import update_config


# https://stackoverflow.com/questions/48145992/showing-json-field-in-django-admin
class PrettyJSONWidget(widgets.Textarea):
    def format_value(self, value):
        try:
            value = json.dumps(json.loads(value), indent=2, sort_keys=True)
            # these lines will try to adjust size of TextArea to fit to content
            row_lengths = [len(r) for r in value.split("\n")]
            self.attrs["rows"] = min(max(len(row_lengths) + 2, 10), 30)
            self.attrs["cols"] = min(max(max(row_lengths) + 2, 40), 120)
            self.attrs["readonly"] = True
            return value
        except Exception:  # pylint: disable=broad-except
            return super().format_value(value)


@admin.register(AddOn)
class AddOnAdmin(admin.ModelAdmin):
    list_display = [
        "display_name",
        "user",
        "repository",
        "access",
        "error",
        "removed",
        "featured",
        "default",
    ]
    list_select_related = ["github_account__user", "organization"]
    list_filter = ["access", "removed", "featured", "default", "error"]
    autocomplete_fields = ["organization"]
    formfield_overrides = {JSONField: {"widget": PrettyJSONWidget}}
    search_fields = ["name", "repository"]
    readonly_fields = ["name", "repository", "github_account", "github_installation"]
    fields = [
        "name",
        "repository",
        "github_account",
        "github_installation",
        "parameters",
        "organization",
        "access",
        "error",
        "removed",
        "featured",
        "default",
    ]

    def get_urls(self):
        """Add custom URLs here"""
        urls = super().get_urls()
        my_urls = [
            path(
                "update_config/<int:pk>/<path:repository>/",
                self.admin_site.admin_view(self.update_config),
                name="addon-update-config",
            )
        ]
        return my_urls + urls

    def update_config(self, request, pk, repository):
        update_config.delay(repository)
        messages.success(request, f"Updating from repo {repository}")
        return HttpResponseRedirect(reverse("admin:addons_addon_change", args=[pk]))

    def display_name(self, obj):
        """Set a default if empty"""
        if obj.name:
            return obj.name

        return "(None)"

    display_name.short_description = "Name"


@admin.register(AddOnEvent)
class AddOnEventAdmin(admin.ModelAdmin):
    list_display = ["addon", "user", "event"]
    list_select_related = ["addon", "user"]
    list_filter = ["event"]
    date_hierarchy = "updated_at"
    autocomplete_fields = ["addon", "user"]


@admin.register(AddOnRun)
class AddOnRunAdmin(admin.ModelAdmin):
    list_display = (
        "addon",
        "user",
        "run_id",
        "status",
        "rating",
        "credits_spent",
        "created_at",
        "updated_at",
    )
    list_select_related = ("addon", "user")
    search_fields = ("addon__name", "user__email", "status")
    date_hierarchy = "created_at"
    actions = ["export_runs_as_csv"]
    readonly_fields = [f.name for f in AddOnRun._meta.fields]

    def get_search_results(self, request, queryset, search_term):
        """Avoid collation issue when searching add-on runs"""
        if search_term:
            queryset = queryset.filter(
                Q(addon__name__icontains=search_term)
                | Q(user__email__icontains=search_term)
                | Q(status__icontains=search_term)
            )
            use_distinct = False
        else:
            use_distinct = False
        return queryset, use_distinct

    def export_runs_as_csv(self, request, queryset):
        """Export selected Add-On Runs to CSV."""
        field_names = [
            "addon_id",
            "addon_name",
            "user_id",
            "user_name",
            "user_email",
            "run_id",
            "status",
            "rating",
            "credits_spent",
            "created_at",
            "updated_at",
        ]

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=addon_runs.csv"

        writer = csv.writer(response)
        writer.writerow(field_names)

        limited_queryset = queryset.select_related("addon", "user").only(
            "addon_id",
            "user_id",
            "run_id",
            "status",
            "rating",
            "credits_spent",
            "created_at",
            "updated_at",
            "addon__name",
            "user__name",
            "user__email",
        )

        for run in limited_queryset.iterator(chunk_size=settings.CSV_EXPORT_CHUNK_SIZE):
            writer.writerow(
                [
                    run.addon_id,
                    run.addon.name,
                    run.user_id,
                    run.user.name,
                    run.user.email,
                    run.run_id,
                    run.status,
                    run.rating,
                    run.credits_spent,
                    run.created_at.isoformat(),
                    run.updated_at.isoformat(),
                ]
            )

        return response

    export_runs_as_csv.short_description = "Export selected runs to CSV"


@admin.register(AddOnDisableLog)
class AddOnDisableLogAdmin(admin.ModelAdmin):
    """Add On Disable Log Admin"""

    list_display = [
        "get_addon_name",
        "get_user_name",
        "created_at",
        "previous_event_state",
        "reverted",
    ]
    list_select_related = [
        "addon_event__addon",
        "addon_event__user",
    ]
    list_filter = ["reverted"]
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "addon_event", "previous_event_state")

    actions = ["revert_addon_event"]

    def get_addon_name(self, obj):
        return obj.addon_event.addon.name

    get_addon_name.short_description = "Addon Name"

    def get_user_name(self, obj):
        return obj.addon_event.user.username

    get_user_name.short_description = "User Name"

    def revert_addon_event(self, request, queryset):
        for log in queryset:
            log.revert_event()
        self.message_user(request, "Events reverted successfully.")

    revert_addon_event.short_description = "Re-enable add-on(s)"


@admin.register(GitHubAccount)
class GitHubAccountAdmin(admin.ModelAdmin):
    list_display = ["name", "user"]
    list_select_related = ["user"]
    fields = ["user", "name", "uid"]
    readonly_fields = ["user", "name", "uid"]
    search_fields = ["name"]


@admin.register(GitHubInstallation)
class GitHubInstallationAdmin(admin.ModelAdmin):
    list_display = ["name", "account", "removed"]
    list_select_related = ["account"]
    fields = ["account", "name", "iid", "removed"]
    readonly_fields = ["account", "name", "iid", "removed"]
    search_fields = ["name"]


@admin.register(VisualAddOn)
class VisualAddOnAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "user",
        "organization",
        "access",
    ]
    list_select_related = ["user", "organization"]
    list_filter = ["access"]
    autocomplete_fields = ["user", "organization"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}
    fields = [
        "name",
        "slug",
        "url",
        "user",
        "organization",
        "access",
        "created_at",
        "updated_at",
    ]
    readonly_fields = ["created_at", "updated_at"]
