# Django
from django.apps import AppConfig


class AddOnsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "documentcloud.addons"

    def ready(self):
        # pylint: disable=unused-import
        # load signals
        # DocumentCloud
        import documentcloud.addons.signals
