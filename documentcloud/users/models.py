# Django
from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.contrib.postgres.fields import CICharField, CIEmailField
from django.core.cache import cache
from django.db import models, transaction
from django.http.request import urlencode
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _

# Standard Library
from uuid import uuid4

# Third Party
import requests

# DocumentCloud
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.organizations.models import Organization
from documentcloud.squarelet.utils import squarelet_get
from documentcloud.users.managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """User model for DocumentCloud"""

    uuid = models.UUIDField(
        _("UUID"), unique=True, editable=False, default=uuid4, db_index=True
    )
    name = models.CharField(_("name of user"), max_length=255)
    email = CIEmailField(_("email"), unique=True, null=True)
    username = CICharField(_("username"), max_length=150, unique=True)
    avatar_url = models.URLField(_("avatar url"), blank=True, max_length=255)
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )

    email_failed = models.BooleanField(
        _("email failed"),
        default=False,
        help_text=_("Has an email we sent to this user's email address failed?"),
    )

    created_at = AutoCreatedField(_("created at"))
    updated_at = AutoLastModifiedField(_("updated at"))

    # preferences
    use_autologin = models.BooleanField(
        _("use autologin"),
        default=True,
        help_text=(
            "Links you receive in emails from us will contain"
            " a token to automatically log you in"
        ),
    )

    USERNAME_FIELD = "username"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["email"]

    objects = UserManager()

    def __str__(self):
        return self.username

    @property
    def date_joined(self):
        """Alias date joined to create_at for third party apps"""
        return self.created_at

    def get_full_name(self):
        return self.name

    @property
    def organization(self):
        """Get the user's active organization"""
        return (
            self.memberships.select_related("organization")
            .get(active=True)
            .organization
        )

    @organization.setter
    def organization(self, organization):
        """Set the user's active organization"""
        if not organization.has_member(self):
            raise ValueError(
                "Cannot set a user's active organization to an organization "
                "they are not a member of"
            )
        with transaction.atomic():
            self.memberships.filter(active=True).update(active=False)
            self.memberships.filter(organization=organization).update(active=True)

    @property
    def individual_organization(self):
        """Get the user's individual organization
        There should always be exactly one individual organization,
        which has a matching UUID
        """
        return Organization.objects.get(uuid=self.uuid)

    def wrap_url(self, link, **extra):
        """Wrap a URL for autologin"""

        link = "{}?{}".format(link, urlencode(extra))

        if not self.use_autologin:
            return f"{settings.DOCCLOUD_URL}{link}"

        url_auth_token = self.get_url_auth_token()
        if not url_auth_token:
            # if there was an error getting the auth token from squarelet,
            # just send the email without the autologin links
            return f"{settings.DOCCLOUD_URL}{link}"

        documentcloud_url = "{}{}?{}".format(
            settings.DOCCLOUD_URL, reverse("acct-login"), urlencode({"next": link})
        )
        params = {"next": documentcloud_url, "url_auth_token": url_auth_token}
        return "{}/accounts/login/?{}".format(settings.SQUARELET_URL, urlencode(params))

    def get_url_auth_token(self):
        """Get a URL auth token for the user
        Cache it so a single email will use a single auth token"""

        def get_url_auth_token_squarelet():
            """Get the URL auth token from squarelet"""
            try:
                resp = squarelet_get(f"/api/url_auth_tokens/{self.uuid}/")
                resp.raise_for_status()
            except requests.exceptions.RequestException:
                return None
            return resp.json().get("url_auth_token")

        return cache.get_or_set(
            f"url_auth_token:{self.uuid}", get_url_auth_token_squarelet, 60 * 5
        )
