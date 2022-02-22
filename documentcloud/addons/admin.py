# Django
from django.contrib import admin

# Third Party
from reversion.admin import VersionAdmin

# DocumentCloud
from documentcloud.addons.models import AddOn


@admin.register(AddOn)
class AddOnAdmin(VersionAdmin):
    list_display = ["name", "user", "organization", "repository"]
    autocomplete_fields = ["user", "organization"]
