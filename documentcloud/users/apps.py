# Django
from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = "documentcloud.users"

    def ready(self):
        # pylint: disable=unused-import
        # load signals
        # DocumentCloud
        import documentcloud.users.signals
