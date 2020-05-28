# Django
from django.contrib import admin

# Third Party
from reversion.admin import VersionAdmin
from squarelet_auth.users.admin import UserAdmin as SAUserAdmin

# DocumentCloud
from documentcloud.users.models import User


@admin.register(User)
class UserAdmin(VersionAdmin, SAUserAdmin):
    """User Admin"""
