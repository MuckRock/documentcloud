# Django
from django.db import models
from django.utils.translation import gettext_lazy as _

# Third Party
from squarelet_auth.users.models import User as SAUser

# DocumentCloud
from documentcloud.core.choices import Language
from documentcloud.users.managers import UserManager


class User(SAUser):
    """User model for DocumentCloud"""

    language = models.CharField(
        _("language"),
        max_length=3,
        choices=Language.choices,
        default="eng",
        blank=True,
        help_text=_("The interface language for this user"),
    )
    document_language = models.CharField(
        _("document language"),
        max_length=3,
        choices=Language.choices,
        default="eng",
        blank=True,
        help_text=_("The default language for documents uploaded by this user"),
    )

    objects = UserManager()
