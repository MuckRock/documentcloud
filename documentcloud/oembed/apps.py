# Django
from django.apps import AppConfig


class OembedConfig(AppConfig):
    name = "documentcloud.oembed"

    def ready(self):
        # Django
        from django.utils.module_loading import autodiscover_modules

        autodiscover_modules("oembed")
