# Django
from celery import shared_task
from django.core.management import call_command


@shared_task
def recompute_user_and_org_stats():
    """Nightly recompute of stored document counts on stats rows."""
    call_command("recompute_user_and_org_stats")
