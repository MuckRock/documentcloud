# Django
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

# Third Party
from squarelet_auth.organizations.models import Membership

# DocumentCloud
from documentcloud.users.models import User

if hasattr(settings, "MOESIF_MIDDLEWARE"):
    # pylint: disable=import-error
    from moesifapi.moesif_api_client import MoesifAPIClient

    api_client = MoesifAPIClient(settings.MOESIF_MIDDLEWARE["APPLICATION_ID"]).api

    @receiver(
        post_save, sender=User, dispatch_uid="documentcloud.user.signals.moesif_user"
    )
    def moesif_user(instance, **_kwargs):
        data = {
            "user_id": str(instance.pk),
            "metadata": {
                "email": instance.email,
                "name": instance.name,
                "photo_url": instance.avatar_url,
            },
        }
        try:
            # the organization may not be set yet, skip it if not set
            data["company_id"] = str(instance.organization.pk)
        except Membership.DoesNotExist:
            pass
        api_client.update_user(data)
