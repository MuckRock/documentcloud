# Django
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

# DocumentCloud
from documentcloud.addons.models import AddOn


@receiver(user_logged_in, dispatch_uid="documentcloud.user.signals.default_addons")
def default_addons(sender, user, request, **kwargs):
    """Activate default add-ons for user on login if they do not have any add-ons
    activated"""
    # pylint: disable=unused-argument

    if not user.active_addons.exists():
        user.active_addons.set(AddOn.objects.filter(default=True))


@receiver(post_save, dispatch_uid="documentcloud.users.signals.touch_last_upload")
def touch_last_upload(sender, instance, created, **kwargs):
    """Record upload recency when a user creates a new document"""
    # DocumentCloud
    from documentcloud.documents.models import Document
    from documentcloud.organizations.stats_api.models import OrganizationStats
    from documentcloud.users.stats_api.models import UserStats

    if sender is not Document or not created:
        return

    now = timezone.now()
    UserStats.objects.update_or_create(
        user_id=instance.user_id,
        defaults={"last_upload_at": now},
    )

    if not instance.organization.individual:
        OrganizationStats.objects.update_or_create(
            organization_id=instance.organization_id,
            defaults={"last_upload_at": now},
        )
