# Django
from django.utils.text import slugify as django_slugify

# Third Party
from unidecode import unidecode


def slugify(text):
    """Unicode safe slugify function, which also handles blank slugs"""
    slug = django_slugify(unidecode(text))
    return slug if slug else "untitled"
