# Django
from django.db import models
from django.db.models.aggregates import Max
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce
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
        max_length=8,
        choices=Language.choices,
        default="eng",
        blank=True,
        help_text=_("The interface language for this user"),
    )
    document_language = models.CharField(
        _("document language"),
        max_length=8,
        choices=Language.choices,
        default="eng",
        blank=True,
        help_text=_("The default language for documents uploaded by this user"),
    )
    active_addons = models.ManyToManyField(
        verbose_name=_("active add-ons"),
        to="addons.AddOn",
        related_name="users",
        help_text=_("Add-Ons shown for this user"),
    )
    mailkey = models.UUIDField(
        _("mailkey"),
        null=True,
        help_text=_("Mail key for uploading documents via email"),
    )

    objects = UserManager()

    @property
    def feature_level(self):
        """The user's highest feature level among all organizations they belong to"""
        return self.organizations.annotate(
            feature_level=Coalesce(
                Cast(
                    KeyTextTransform("feature_level", "entitlement__resources"),
                    models.IntegerField(),
                ),
                0,
            )
        ).aggregate(max=Max("feature_level"))["max"]
