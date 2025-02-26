# Django
from django.utils.text import slugify as django_slugify

# Standard Library
from itertools import zip_longest

# Third Party
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from unidecode import unidecode


class ProcessingTokenAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "documentcloud.core.authentication.ProcessingTokenAuthentication"
    name = "ProcessingTokenAuthentication"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": (
                "Custom token-based authentication using"
                " the 'processing-token' scheme.\n\n"
                "Clients must include an Authorization header with the token:\n\n"
                "    Authorization: processing-token <your_token>"
            ),
        }


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
    excluded_endpoints = ["statistics", "sidekick", "flatpage", "legacy", "dates"]
    for path, path_regex, method, callback in endpoints:
        if "api" in path and not any(
            excluded in path for excluded in excluded_endpoints
        ):
            filtered.append((path, path_regex, method, callback))
    return filtered
