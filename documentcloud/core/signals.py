# Django
from django.contrib.flatpages.models import FlatPage
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(
    post_save,
    sender=FlatPage,
    dispatch_uid="documentcloud.core.signals.flatpage_invalidate_cache",
)
def flatpage_invalidate_cache(instance, **kwargs):
    key = make_template_fragment_key("flatpage", [instance.pk])
    cache.delete(key)
