# Django
from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = "documentcloud.users"

    def ready(self):
        # require squarelet login for admin
        from django.contrib.auth.decorators import login_required
        from django.contrib import admin

        admin.site.login = login_required(admin.site.login)
