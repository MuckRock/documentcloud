# Django
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

# DocumentCloud
from documentcloud.organizations.models import Organization

if hasattr(settings, "MOESIF_MIDDLEWARE"):
    # pylint: disable=import-error
    from moesifapi.moesif_api_client import MoesifAPIClient

    api_client = MoesifAPIClient(settings.MOESIF_MIDDLEWARE["APPLICATION_ID"]).api

    @receiver(
        post_save,
        sender=Organization,
        dispatch_uid="documentcloud.user.signals.moesif_organization",
    )
    def moesif_organization(instance, **_kwargs):
        api_client.update_company(
            {
                "company_id": str(instance.pk),
                "metadata": {
                    "name": instance.name,
                    "photo_url": instance.avatar_url,
                    "plan": instance.entitlement.name if instance.entitlement else None,
                    "verified": instance.verified_journalist,
                },
            }
        )
