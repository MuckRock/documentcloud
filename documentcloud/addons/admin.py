# Django
from django.contrib import admin
from django.db.models import JSONField
from django.forms import widgets

# Standard Library
import json

# Third Party
from reversion.admin import VersionAdmin

# DocumentCloud
from documentcloud.addons.models import AddOn


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
class AddOnAdmin(VersionAdmin):
    list_display = ["name", "user", "organization", "repository"]
    autocomplete_fields = ["user", "organization"]
    formfield_overrides = {JSONField: {"widget": PrettyJSONWidget}}
