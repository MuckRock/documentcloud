# Django
from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "documentcloud.core"

    def ready(self):
        # pylint: disable=unused-import
        # load signals
        from documentcloud.core.signals import flatpage_invalidate_cache
