# Django
from django.contrib import admin, messages
from django.db.models import JSONField
from django.forms import widgets
from django.http.response import HttpResponseRedirect
from django.urls import path, reverse

# Standard Library
import json

# DocumentCloud
from documentcloud.addons.models import AddOn
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
            return value
        except Exception:  # pylint: disable=broad-except
            return super(PrettyJSONWidget, self).format_value(value)


@admin.register(AddOn)
class AddOnAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "organization", "repository"]
    autocomplete_fields = ["user", "organization"]
    formfield_overrides = {JSONField: {"widget": PrettyJSONWidget}}

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
