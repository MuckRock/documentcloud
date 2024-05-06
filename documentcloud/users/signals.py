# Django
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

# DocumentCloud
from documentcloud.addons.models import AddOn


@receiver(user_logged_in, dispatch_uid="documentcloud.user.signals.default_addons")
def default_addons(sender, user, request, **kwargs):
    """Activate default add-ons for user on login if they do not have any add-ons
    activated"""
    # pylint: disable=unused-argument

    if not user.active_addons.exists():
        user.active_addons.set(AddOn.objects.filter(default=True))
