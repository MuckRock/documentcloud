# Django
from django.apps import AppConfig


class SidekickConfig(AppConfig):
    name = "documentcloud.sidekick"

    def ready(self):
        # pylint: disable=unused-import
        # load signals
        import documentcloud.sidekick.signals
