# Django
from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    name = "documentcloud.organizations"

    def ready(self):
        # pylint: disable=unused-import
        # load signals
        # DocumentCloud
        import documentcloud.organizations.signals
