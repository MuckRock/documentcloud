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


def record_uploads(user_ids=None, organization_ids=None, when=None):
    """
    Bump the upload watermark for the given uploaders.
    Called explicitly at document-creation sites (perform_create and the mailgun
    view) rather than via a post_save signal. Updates existing stats
    rows only.
    """
    when = when or timezone.now()
    if user_ids:
        UserStats.objects.filter(user_id__in=user_ids).update(last_upload_at=when)
    if organization_ids:
        OrganizationStats.objects.filter(organization_id__in=organization_ids).update(
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
