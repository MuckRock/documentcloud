# Django
from django.contrib import admin

# Third Party
from reversion.admin import VersionAdmin

# DocumentCloud
from documentcloud.plugins.models import Plugin


@admin.register(Plugin)
class PluginAdmin(VersionAdmin):
    list_display = ["name", "user", "organization", "repository"]
    autocomplete_fields = ["user", "organization"]
