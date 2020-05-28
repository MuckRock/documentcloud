# Django
from django.contrib import admin
from django.urls import reverse
from django.utils.safestring import mark_safe

# Third Party
from reversion.admin import VersionAdmin

# DocumentCloud
from documentcloud.organizations.models import Organization
from documentcloud.users.models import User


@admin.register(Organization)
class OrganizationAdmin(VersionAdmin):
    """Organization Admin"""

    list_display = ("name", "entitlement", "private", "individual")
    list_filter = ("entitlement", "private", "individual")
    search_fields = ("name", "users__username")
    fields = (
        "uuid",
        "name",
        "slug",
        "private",
        "individual",
        "entitlement",
        "card",
        "pages_per_month",
        "monthly_pages",
        "number_pages",
        "date_update",
    )
    readonly_fields = (
        "uuid",
        "name",
        "slug",
        "private",
        "individual",
        "entitlement",
        "card",
        "pages_per_month",
        "date_update",
    )
    list_select_related = ("entitlement",)

    def get_fields(self, request, obj=None):
        """Only add user link for individual organizations"""
        if obj and obj.individual:
            return ("user_link",) + self.fields
        else:
            return self.fields

    def get_readonly_fields(self, request, obj=None):
        """Only add user link for individual organizations"""
        if obj and obj.individual:
            return ("user_link",) + self.readonly_fields
        else:
            return self.readonly_fields

    @mark_safe
    def user_link(self, obj):
        """Link to the individual org's user"""
        user = User.objects.get(uuid=obj.uuid)
        link = reverse("admin:users_user_change", args=(user.pk,))
        return '<a href="%s">%s</a>' % (link, user.username)

    user_link.short_description = "User"
