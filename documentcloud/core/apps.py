# Django
from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "documentcloud.core"

    def ready(self):
        # pylint: disable=unused-import
        # load signals
        # DocumentCloud
        from documentcloud.core.signals import flatpage_invalidate_cache
