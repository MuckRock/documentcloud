# Django
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver

# DocumentCloud
from documentcloud.addons.models import AddOn
from documentcloud.users.models import User
from documentcloud.users.stats_api.models import UserStats


@receiver(user_logged_in, dispatch_uid="documentcloud.user.signals.default_addons")
def default_addons(sender, user, request, **kwargs):
    """Activate default add-ons for user on login if they do not have any add-ons
    activated"""
    # pylint: disable=unused-argument

    if not user.active_addons.exists():
        user.active_addons.set(AddOn.objects.filter(default=True))


@receiver(
    post_save, sender=User, dispatch_uid="documentcloud.users.signals.create_user_stats"
)
def create_user_stats(sender, instance, created, **kwargs):
    """
    Create a UserStats row when a new user is created.
    Users are created by squarelet sync,
    so post_save is the only path that catches every creation.
    get_or_create avoids a duplicate-row error if two requests create the same
    user's stats at once. The receiver only ever creates, never updates,
    so no stats logic lives in the signal.
    """
    # pylint: disable=unused-argument
    if created:
        UserStats.objects.get_or_create(user=instance)
