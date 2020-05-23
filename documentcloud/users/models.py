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
from squarelet_auth.users.models import User as SAUser

# DocumentCloud
from documentcloud.core.choices import Language
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.organizations.models import Organization
from documentcloud.squarelet.utils import squarelet_get
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

    # XXX add to squarelet-auth?
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

    # XXX add to squarelet-auth?
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
