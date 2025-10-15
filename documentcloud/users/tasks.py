# Django
from celery import shared_task

# DocumentCloud
from documentcloud.users.mail import PermissionsDigest


@shared_task
def permission_digest():
    PermissionsDigest().send()
