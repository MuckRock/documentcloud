# Django
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as AuthUserAdmin
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

# Third Party
from reversion.admin import VersionAdmin

# DocumentCloud
from documentcloud.users.models import User


@admin.register(User)
class UserAdmin(VersionAdmin, AuthUserAdmin):
    fieldsets = (
        (None, {"fields": ("uuid", "username", "org_link")}),
        (_("Personal info"), {"fields": ("name", "email")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "created_at", "updated_at")}),
    )
    readonly_fields = (
        "uuid",
        "username",
        "org_link",
        "name",
        "email",
        "last_login",
        "created_at",
        "updated_at",
    )
    list_display = (
        "username",
        "name",
        "email",
        "is_staff",
        "is_superuser",
        "is_active",
    )
    search_fields = ("username", "name", "email")

    @mark_safe
    def org_link(self, obj):
        """Link to the individual org"""
        link = reverse(
            "admin:organizations_organization_change",
            args=(obj.individual_organization.pk,),
        )
        return '<a href="%s">%s</a>' % (link, obj.individual_organization.name)

    org_link.short_description = "Individual Organization"
