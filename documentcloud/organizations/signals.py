# Django
from django.db.models.signals import post_save
from django.dispatch import receiver

# DocumentCloud
from documentcloud.organizations.models import Organization
from documentcloud.organizations.stats_api.models import OrganizationStats


@receiver(
    post_save,
    sender=Organization,
    dispatch_uid="documentcloud.organizations.signals.create_organization_stats",
)
def create_organization_stats(sender, instance, created, **kwargs):
    """Create an OrganizationStats row when a new collective org is created.

    Same rationale as UserStats: post_save is the only hook that catches every path.
    Skips individual orgs, since the org stats endpoint only surfaces collective
    ones. Creates only, never updates, so no stats logic lives here.
    """
    # pylint: disable=unused-argument
    if created and not instance.individual:
        OrganizationStats.objects.get_or_create(organization=instance)
