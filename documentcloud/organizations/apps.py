# Django
from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    name = "documentcloud.organizations"

    def ready(self):
        # DocumentCloud
        import documentcloud.organizations.signals  # pylint: disable=unused-import
