# Django
from django.conf import settings
from django.contrib import admin
from django.http.response import HttpResponse
from django.urls.conf import re_path

# Standard Library
import csv

# Third Party
from squarelet_auth.users.admin import UserAdmin as SAUserAdmin

# DocumentCloud
from documentcloud.users.models import User


@admin.register(User)
class UserAdmin(SAUserAdmin):
    """User Admin"""

    def get_urls(self):
        """Add custom URLs here"""
        urls = super().get_urls()
        my_urls = [
            re_path(
                r"^export/$",
                self.admin_site.admin_view(self.user_export),
                name="users-admin-user-export",
            ),
        ]
        return my_urls + urls

    def user_export(self, request):
        response = HttpResponse(
            content_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="documentcloud_users.csv"'
            },
        )
        writer = csv.writer(response)

        def format_date(date):
            if date is not None:
                return date.strftime("%Y-%m-%d")
            else:
                return ""

        writer.writerow(["username", "name", "email", "last_login", "date_joined"])
        for user in User.objects.only(
            "username", "name", "email", "last_login", "created_at"
        ).iterator(chunk_size=settings.CSV_EXPORT_CHUNK_SIZE):
            writer.writerow(
                [
                    user.username,
                    user.name,
                    user.email,
                    format_date(user.last_login),
                    format_date(user.created_at),
                ]
            )

        return response
