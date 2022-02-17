# Django
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

# Standard Library
import logging
import sys
from datetime import timedelta
from uuid import uuid4

# Third Party
import requests
from squarelet_auth.utils import squarelet_get

# DocumentCloud
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.plugins.querysets import PluginQuerySet, PluginRunQuerySet

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

    @property
    def api_url(self):
        """Get the base API URL"""
        return f"https://api.github.com/repos/{self.repository}"

    @property
    def api_headers(self):
        """Get the authorization header for API calls"""
        return {"Authorization": f"Bearer {self.github_token}"}

    def dispatch(self, uuid, user, documents, query, parameters):
        """Activate the GitHub Action for this plugin"""
        token = self.get_token(user)
        payload = {
            "token": token,
            "base_uri": settings.DOCCLOUD_API_URL + "/api/",
            "id": str(uuid),
            "documents": documents,
            "query": query,
            "data": parameters,
            "user": user.pk,
            "organization": user.organization.pk,
        }
        resp = requests.post(
            f"{self.api_url}/dispatches",
            headers=self.api_headers,
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


class PluginRun(models.Model):
    """Track a particular run of a plugin"""

    objects = PluginRunQuerySet.as_manager()

    plugin = models.ForeignKey(
        verbose_name=_("plugin"),
        to=Plugin,
        on_delete=models.PROTECT,
        related_name="runs",
        help_text=_("The plugin which was ran"),
    )
    user = models.ForeignKey(
        verbose_name=_("user"),
        to="users.User",
        on_delete=models.PROTECT,
        related_name="plugin_runs",
        help_text=_("The user who ran this plugin"),
    )
    uuid = models.UUIDField(
        _("UUID"),
        unique=True,
        editable=False,
        default=uuid4,
        db_index=True,
        help_text=_("Unique ID to track plugin runs"),
    )
    run_id = models.IntegerField(
        _("run_id"),
        unique=True,
        null=True,
        help_text=_("The GitHub Action run_id for this run"),
    )
    # https://docs.github.com/en/rest/reference/checks#create-a-check-run
    status = models.CharField(
        _("status"),
        max_length=25,
        help_text=_("The status of this run"),
        default="queued",
    )
    progress = models.PositiveSmallIntegerField(
        _("progress"),
        help_text=_("The progress as a percent done of this run"),
        default=0,
    )

    created_at = AutoCreatedField(
        _("created at"), help_text=_("Timestamp of when the document was created")
    )
    updated_at = AutoLastModifiedField(
        _("updated at"), help_text=_("Timestamp of when the document was last updated")
    )

    def __str__(self):
        return f"Run: {self.plugin_id} - {self.created_at}"

    def find_run_id(self):
        """Find the GitHub Actions run ID from the PluginRun's UUID"""
        # XXX error checking
        date_filter = (self.created_at - timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M"
        )

        resp = requests.get(
            f"{self.plugin.api_url}/actions/runs?created=%3E{date_filter}",
            headers=self.plugin.api_headers,
        )
        runs = resp.json()["workflow_runs"]

        logger.info("[FIND RUN ID] len(runs) %s", len(runs))
        if len(runs) > 0:
            for workflow in runs:
                jobs_url = workflow["jobs_url"]
                logger.info("[FIND RUN ID] get jobs_url %s", jobs_url)

                resp = requests.get(jobs_url, headers=self.plugin.api_headers)

                jobs = resp.json()["jobs"]
                logger.info("[FIND RUN ID] len(jobs) %s", len(jobs))
                if len(jobs) > 0:
                    # the ID is located at the second step of the first job
                    job = jobs[0]
                    steps = job["steps"]
                    logger.info("[FIND RUN ID] len(steps) %s", len(steps))
                    if len(steps) >= 2:
                        second_step = steps[1]
                        logger.info(
                            "[FIND RUN ID] second step name %s", second_step["name"]
                        )
                        if second_step["name"] == self.uuid:
                            return job["run_id"]

        # return None if fail to find the run ID
        return None

    def get_status(self):
        """Get the status from the GitHub API"""

        if not self.run_id:
            return None

        resp = requests.get(
            f"{self.plugin.api_url}/actions/runs/{self.run_id}",
            headers=self.plugin.api_headers,
        )
        # XXX error check
        status = resp.json()["status"]
        if status == "completed":
            # if we are completed, use the conclusion as the status
            status = resp.json()["conclusion"]
        return status
