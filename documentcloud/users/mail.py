# Django
from django.conf import settings
from django.contrib.auth.models import Group

# Standard Library
from datetime import date

# DocumentCloud
from documentcloud.core.mail import Email
from documentcloud.users.models import User


class PermissionsDigest(Email):
    """A digest that provides an overview of who has what permissions"""

    template = "users/email/permissions.html"

    def __init__(self, **kwargs):
        kwargs["subject"] = f"{date.today()} DocumentCloud Permissions Digest"
        kwargs["to"] = settings.PERMISSIONS_DIGEST_EMAILS
        kwargs["extra_context"] = self.get_context()
        super().__init__(**kwargs)

    def get_context(self):
        return {
            "superusers": User.objects.filter(is_superuser=True),
            "staff": User.objects.filter(is_staff=True),
            "groups": Group.objects.prefetch_related("user_set"),
            "user_permissions": User.user_permissions.through.objects.select_related(
                "user",
                "permission",
            ),
        }
