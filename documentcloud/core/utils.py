# Django
from django.utils import timezone
from django.utils.text import slugify as django_slugify

# Standard Library
from itertools import zip_longest

# Third Party
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from unidecode import unidecode

# DocumentCloud
from documentcloud.organizations.stats_api.models import OrganizationStats
from documentcloud.users.stats_api.models import UserStats


class SquareletJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """Simply lets DRF advertise that you can use a JWT from Accounts to auth"""

    target_class = "documentcloud.core.authentication.SquareletJWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "JWT bearer token issued by MuckRock Accounts. "
                "Obtain a token from https://accounts.muckrock.com/api/token/ "
                "and refresh it at https://accounts.muckrock.com/api/refresh/. "
                "Access tokens are valid for 5 minutes and "
                "refresh tokens are valid for 24 hours"
                "Send it as `Authorization: Bearer <token>`."
            ),
        }


def hide_processing_token(result, _generator, request, _public):
    """Since processing token is defined, we need to have it here
    but pop it from security schemes as we are the only ones to use this token style
    """
    result.get("components", {}).get("securitySchemes", {}).pop(
        "ProcessingTokenAuthentication", None
    )
    for path_item in result.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict) and "security" in operation:
                operation["security"] = [
                    scheme
                    for scheme in operation["security"]
                    if "ProcessingTokenAuthentication" not in scheme
                ]
    return result


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


def format_date(date):
    if date is None:
        return None
    return date.replace(tzinfo=None).isoformat() + "Z"


def record_uploads(user_id=None, organization_id=None, when=None):
    """
    Bump the upload watermark for the given uploaders.
    Called explicitly at document-creation sites (perform_create and the mailgun
    view) rather than via a post_save signal. Updates existing stats
    rows only.
    """
    when = when or timezone.now()
    if user_id:
        UserStats.objects.filter(user_id=user_id).update(last_upload_at=when)
    if organization_id:
        OrganizationStats.objects.filter(organization_id=organization_id).update(
            last_upload_at=when
        )


def record_ai_credit_use(user_id=None, organization_id=None, when=None):
    """
    Bump the AI-credit-use watermark on the user and org stats rows.
    Called explicitly from Organization.use_ai_credits.
    Balances are read live via get_total_* calls, so this only records when
    credits were last used.
    """
    when = when or timezone.now()
    if user_id:
        UserStats.objects.filter(user_id=user_id).update(last_ai_credit_at=when)
    if organization_id:
        OrganizationStats.objects.filter(organization_id=organization_id).update(
            last_ai_credit_at=when
        )
