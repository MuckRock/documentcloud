# Django
from django.conf import settings
from django.contrib.flatpages.models import FlatPage
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.db.models.signals import post_save
from django.dispatch import receiver

# Standard Library
import logging
import re

# Third Party
from corsheaders.signals import check_request_enabled

ALLOW_PATHS = [re.compile(p) for p in settings.CORS_ALLOW_PATHS]

logger = logging.getLogger(__name__)


@receiver(
    post_save,
    sender=FlatPage,
    dispatch_uid="documentcloud.core.signals.flatpage_invalidate_cache",
)
def flatpage_invalidate_cache(instance, **kwargs):
    # pylint: disable=unused-argument
    key = make_template_fragment_key("flatpage", [instance.pk])
    cache.delete(key)


@receiver(check_request_enabled, dispatch_uid="documentcloud.core.signals.check_cors")
def check_cors(sender, request, **kwargs):
    """Allow anonymous GET requests to the pre-defined allowed paths"""
    # pylint: disable=unused-argument
    logger.debug(
        "check cors\npath: %s\nmethod: %s\nanonymous: %s\nmatch: %s",
        request.path,
        request.method,
        request.user.is_anonymous,
        any(p.match(request.path) for p in ALLOW_PATHS),
    )
    return (
        request.method.lower() == "get"
        and request.user.is_anonymous
        and any(p.match(request.path) for p in ALLOW_PATHS)
    )
