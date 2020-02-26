# Django
from django.core.exceptions import ImproperlyConfigured

# DocumentCloud
from documentcloud.oembed.oembed import OEmbed

registry = []


def register(oembed_class):
    if not issubclass(oembed_class, OEmbed):
        raise ImproperlyConfigured("Only subclasses of OEmbed may be registered")
    registry.append(oembed_class())
    return oembed_class
