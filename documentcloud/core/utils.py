# Django
from django.utils.text import slugify as django_slugify

# Standard Library
from itertools import zip_longest

# Third Party
from unidecode import unidecode


def slugify(text):
    """Unicode safe slugify function, which also handles blank slugs"""
    slug = django_slugify(unidecode(text))
    return slug[:255] if slug else "untitled"


def grouper(iterable, num, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * num
    return zip_longest(*args, fillvalue=fillvalue)


def custom_preprocessing_hook(endpoints):
    filtered = []
    for path, path_regex, method, callback in endpoints:
        if "api" in path and "statistics" not in path:
            filtered.append((path, path_regex, method, callback))
    return filtered