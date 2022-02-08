# Django
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

# Standard Library
import logging
import sys

# Third Party
import requests
from squarelet_auth.utils import squarelet_get

# DocumentCloud
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.plugins.querysets import PluginQuerySet

logger = logging.getLogger(__name__)


class Plugin(models.Model):

    objects = PluginQuerySet.as_manager()

    user = models.ForeignKey(
        verbose_name=_("user"),
        to="users.User",
        on_delete=models.PROTECT,
        related_name="plugins",
        help_text=_("The user who created this plugin"),
    )
    organization = models.ForeignKey(
        verbose_name=_("organization"),
        to="organizations.Organization",
        on_delete=models.PROTECT,
        related_name="plugins",
        help_text=_("The organization this plugin was created within"),
    )

    name = models.CharField(_("name"), max_length=255, help_text=_("The plugin's name"))
    repository = models.CharField(
        _("repository"), max_length=140, help_text=_("The plugin's GitHub repository")
    )
    github_token = models.CharField(
        _("github token"),
        max_length=40,
        help_text=_("The token to access the plugin's GitHub repository"),
    )

    parameters = models.JSONField(
        _("parameters"), help_text=_("The parameters for this plugin")
    )

    created_at = AutoCreatedField(
        _("created at"), help_text=_("Timestamp of when the document was created")
    )
    updated_at = AutoLastModifiedField(
        _("updated at"), help_text=_("Timestamp of when the document was last updated")
    )

    def __str__(self):
        return self.name

    def get_token(self, user):
        """Get a JWT from squarelet for the plugin to be able to authenticate
        itself to the DocumentCloud API
        """
        try:
            resp = squarelet_get("/api/access_tokens/{}/".format(user.uuid))
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "Error getting token for Add-On: %s", exc, exc_info=sys.exc_info()
            )
            raise
        return resp.json().get("access_token")

    def dispatch(self, user, documents, query, parameters):
        """Activate the GitHub Action for this plugin"""
        token = self.get_token(user)
        payload = {
            "token": token,
            "base_uri": settings.DOCCLOUD_API_URL + "/api/",
            "documents": documents,
            "query": query,
            "data": parameters,
            "user": user.pk,
            "organization": user.organization.pk,
        }
        resp = requests.post(
            f"https://api.github.com/repos/{self.repository}/dispatches",
            headers={"Authorization": f"Bearer {self.github_token}"},
            json={"event_type": self.name, "client_payload": payload},
        )
        resp.raise_for_status()

    def validate(self, parameters):
        """Validate the passed in parameters

        This can eventually be expanded to do more then just check for missing
        parameters
        """
        missing = []
        for parameter in self.parameters:
            if parameter["name"] not in parameters:
                missing.append(parameter["name"])
        return missing
