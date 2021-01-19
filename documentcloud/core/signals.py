# Django
from django.contrib.flatpages.models import FlatPage
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.db.models.signals import post_save
from django.dispatch import receiver

# Third Party
from corsheaders.signals import check_request_enabled


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
    """Allow anonymous GET/OPTIONS requests to the pre-defined allowed paths"""
    # pylint: disable=unused-argument
    anonymous = not hasattr(request, "user") or request.user.is_anonymous
    return request.method.lower() in ["get", "options"] and anonymous
