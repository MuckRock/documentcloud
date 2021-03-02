# Django
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

# DocumentCloud
from documentcloud.users.models import User

if hasattr(settings, "MOESIF_MIDDLEWARE"):
    from moesifapi.moesif_api_client import MoesifAPIClient

    api_client = MoesifAPIClient(settings.MOESIF_MIDDLEWARE["APPLICATION_ID"]).api

    @receiver(
        post_save, sender=User, dispatch_uid="documentcloud.user.signals.moesif_user"
    )
    def moesif_user(instance, **_kwargs):
        api_client.update_user(
            {
                "user_id": str(instance.pk),
                "company_id": str(instance.organization.pk),
                "metadata": {
                    "email": instance.email,
                    "name": instance.name,
                    "photo_url": instance.avatar_url,
                },
            }
        )
