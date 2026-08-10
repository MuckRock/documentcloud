# Django
from django.utils import timezone


def record_upload(user_id, organization_id, organization_individual):
    # DocumentCloud
    from documentcloud.organizations.stats_api.models import OrganizationStats
    from documentcloud.users.stats_api.models import UserStats

    now = timezone.now()
    UserStats.objects.update_or_create(
        user_id=user_id, defaults={"last_upload_at": now}
    )
    if not organization_individual:
        OrganizationStats.objects.update_or_create(
            organization_id=organization_id, defaults={"last_upload_at": now}
        )
