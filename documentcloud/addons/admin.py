# Django
from django.contrib import admin, messages
from django.db.models import JSONField
from django.forms import widgets
from django.http.response import HttpResponseRedirect
from django.urls import path, reverse

# Standard Library
import json

# DocumentCloud
from documentcloud.addons.models import (
    AddOn,
    AddOnEvent,
    GitHubAccount,
    GitHubInstallation,
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
            self.attrs["disabled"] = True
            return value
        except Exception:  # pylint: disable=broad-except
            return super(PrettyJSONWidget, self).format_value(value)


@admin.register(AddOn)
class AddOnAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "organization", "repository", "access", "removed"]
    list_select_related = ["github_account__user", "organization"]
    list_filter = ["access", "removed"]
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


@admin.register(AddOnEvent)
class AddOnEventAdmin(admin.ModelAdmin):
    list_display = ["addon", "user", "event"]
    list_select_related = ["addon", "user"]
    list_filter = ["event"]
    autocomplete_fields = ["addon", "user"]


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
