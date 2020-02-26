# Django
from django.apps import AppConfig


class OembedConfig(AppConfig):
    name = "oembed"

    def ready(self):
        from django.utils.module_loading import autodiscover_modules

        autodiscover_modules("oembed")
