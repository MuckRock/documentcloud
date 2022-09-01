# Django
from django.conf import settings
from django.core.cache import cache
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

# Standard Library
import logging
import sys
from datetime import datetime, timedelta
from uuid import uuid4

# Third Party
import jwt
import requests
import yaml
from squarelet_auth.utils import squarelet_get

# DocumentCloud
from documentcloud.addons.choices import Event
from documentcloud.addons.querysets import (
    AddOnEventQuerySet,
    AddOnQuerySet,
    AddOnRunQuerySet,
)
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.documents.choices import Access

logger = logging.getLogger(__name__)


class AddOn(models.Model):

    objects = AddOnQuerySet.as_manager()

    organization = models.ForeignKey(
        verbose_name=_("organization"),
        to="organizations.Organization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="addons",
        help_text=_("The organization this add-on was created within"),
    )
    access = models.IntegerField(
        _("access"),
        choices=Access.choices,
        default=Access.private,
        help_text=_("Designates who may access this document by default"),
    )

    name = models.CharField(_("name"), max_length=255, help_text=_("The add-on's name"))
    repository = models.CharField(
        _("repository"),
        max_length=140,
        help_text=_("The add-on's GitHub repository"),
        unique=True,
    )
    github_account = models.ForeignKey(
        verbose_name=_("github account"),
        to="addons.GitHubAccount",
        on_delete=models.PROTECT,
        related_name="addons",
        help_text=_("The GitHub account that added this add-on"),
    )
    github_installation = models.ForeignKey(
        verbose_name=_("github installation"),
        to="addons.GitHubInstallation",
        on_delete=models.PROTECT,
        related_name="addons",
        help_text=_("The GitHub installation that contains this add-on"),
    )

    parameters = models.JSONField(
        _("parameters"), default=dict, help_text=_("The parameters for this add-on")
    )

    created_at = AutoCreatedField(
        _("created at"), help_text=_("Timestamp of when the add-on was created")
    )
    updated_at = AutoLastModifiedField(
        _("updated at"), help_text=_("Timestamp of when the add-on was last updated")
    )

    error = models.BooleanField(
        _("error"),
        help_text=_("There was an error with the configuration file"),
        default=False,
    )
    removed = models.BooleanField(
        _("removed"), help_text=_("This add-on was removed"), default=False
    )

    def __str__(self):
        return self.name if self.name else "- Nameless Add-On -"

    def get_tokens(self, user):
        """Get a JWT refresh token an access token from squarelet for the
        add-on to be able to authenticate itself to the DocumentCloud API
        """
        try:
            resp = squarelet_get(f"/api/refresh_tokens/{user.uuid}/")
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "Error getting token for Add-On: %s", exc, exc_info=sys.exc_info()
            )
            raise
        return resp.json()

    @property
    def user(self):
        return self.github_account.user

    @property
    def api_url(self):
        """Get the base API URL"""
        return f"https://api.github.com/repos/{self.repository}"

    @property
    def api_headers(self):
        """Get the authorization header for API calls"""
        return {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

    @property
    def github_token(self):
        return self.github_installation.token

    def dispatch(self, uuid, user, documents, query, parameters, event_id):
        """Activate the GitHub Action for this add-on"""
        # pylint: disable=too-many-arguments
        tokens = self.get_tokens(user)
        payload = {
            "token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "base_uri": settings.DOCCLOUD_API_URL + "/api/",
            "id": str(uuid),
            "documents": documents,
            "query": query,
            "data": parameters,
            "user": user.pk,
            "organization": user.organization.pk,
            "event_id": event_id,
        }
        resp = requests.post(
            f"{self.api_url}/dispatches",
            headers=self.api_headers,
            json={"event_type": self.name, "client_payload": payload},
        )
        resp.raise_for_status()

    def update_config(self):
        """Update the config from the repo's config.yaml file"""
        resp = requests.get(
            f"{self.api_url}/contents/config.yaml",
            headers={**self.api_headers, "Accept": "application/vnd.github.v3.raw"},
        )
        if resp.status_code == 404:
            self.error = True
            self.save()
            return
        resp.raise_for_status()
        try:
            self.parameters = yaml.safe_load(resp.content)
            if "title" in self.parameters:
                self.name = self.parameters["title"]
            self.error = False
        except yaml.YAMLError:
            self.error = True
        self.save()


class AddOnRun(models.Model):
    """Track a particular run of a add-on"""

    objects = AddOnRunQuerySet.as_manager()

    addon = models.ForeignKey(
        verbose_name=_("add-on"),
        to=AddOn,
        on_delete=models.PROTECT,
        related_name="runs",
        help_text=_("The add-on which was ran"),
    )
    event = models.ForeignKey(
        verbose_name=_("event"),
        to="addons.AddOnEvent",
        on_delete=models.PROTECT,
        related_name="runs",
        blank=True,
        null=True,
        help_text=_("The add-on event which triggered this run"),
    )
    user = models.ForeignKey(
        verbose_name=_("user"),
        to="users.User",
        on_delete=models.PROTECT,
        related_name="addon_runs",
        help_text=_("The user who ran this add-on"),
    )
    uuid = models.UUIDField(
        _("UUID"),
        unique=True,
        editable=False,
        default=uuid4,
        db_index=True,
        help_text=_("Unique ID to track add-on runs"),
    )
    run_id = models.BigIntegerField(
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
    message = models.CharField(
        _("message"),
        max_length=255,
        help_text=_("A progress message for the user while the run is in progress"),
        default="",
    )

    file_name = models.CharField(
        _("file_name"),
        max_length=255,
        help_text=_("Path to uploaded file on S3"),
        default="",
    )

    dismissed = models.BooleanField(
        _("dismissed"),
        default=False,
        help_text=_(
            "If this run has been dismissed from view and should no longer be "
            "shown to the user"
        ),
    )

    created_at = AutoCreatedField(
        _("created at"), help_text=_("Timestamp of when the add-on was ran")
    )
    updated_at = AutoLastModifiedField(
        _("updated at"),
        help_text=_("Timestamp of when the add-on run was last updated"),
    )

    def __str__(self):
        return f"Run: {self.addon_id} - {self.created_at}"

    def find_run_id(self):
        """Find the GitHub Actions run ID from the AddOnRun's UUID"""
        date_filter = (self.created_at - timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M"
        )

        url = f"{self.addon.api_url}/actions/runs?created=%3E{date_filter}"
        while url is not None:
            logger.info("[FIND RUN ID] get %s", url)
            resp = requests.get(url, headers=self.addon.api_headers)
            resp.raise_for_status()
            url = resp.links.get("next", {}).get("url")
            resp_json = resp.json()
            runs = resp_json["workflow_runs"]
            logger.info("[FIND RUN ID] total_count %s", resp_json["total_count"])

            for workflow in runs:
                jobs_url = workflow["jobs_url"]
                logger.info("[FIND RUN ID] get jobs_url %s", jobs_url)

                cache_key = f"find_run_id:{jobs_url}"
                cache_results = cache.get(cache_key)
                if cache_results:
                    job_uuid, results = cache_results
                    logger.info(
                        "[FIND RUN ID] get jobs_url %s cache hit %s", jobs_url, job_uuid
                    )
                    if job_uuid == str(self.uuid):
                        return results
                    else:
                        continue

                resp = requests.get(jobs_url, headers=self.addon.api_headers)
                resp.raise_for_status()

                jobs = resp.json()["jobs"]
                logger.info("[FIND RUN ID] len(jobs) %s", len(jobs))

                if len(jobs) > 0 and jobs[0] is not None:
                    # the ID is located at the second step of the first job
                    job = jobs[0]
                    steps = job["steps"]
                    logger.info("[FIND RUN ID] len(steps) %s", len(steps))
                    if len(steps) >= 2:
                        job_uuid = steps[1]["name"]
                        logger.info("[FIND RUN ID] second step name %s", job_uuid)
                        results = (job["run_id"], job["status"], job["conclusion"])
                        cache.set(cache_key, (job_uuid, results), 300)
                        if job_uuid == str(self.uuid):
                            return results

        # return None if fail to find the run ID
        return None

    def set_status(self):
        """Get the status from the GitHub API"""

        if not self.run_id:
            logger.info("[SET STATUS] %s - no run id", self.uuid)
            return

        resp = requests.get(
            f"{self.addon.api_url}/actions/runs/{self.run_id}",
            headers=self.addon.api_headers,
        )
        if resp.status_code != 200:
            logger.info(
                "[SET STATUS] %s - %d request error", self.uuid, resp.status_code
            )
            return
        status = resp.json()["status"]
        if status == "completed":
            # if we are completed, use the conclusion as the status
            status = resp.json()["conclusion"]
        logger.info("[SET STATUS] %s - %s", self.uuid, self.status)
        self.status = status
        self.save(update_fields=["status"])

    def file_path(self, file_name=None):
        if file_name is None:
            file_name = self.file_name
        if file_name:
            return f"{settings.ADDON_BUCKET}/{self.uuid}/{file_name}"
        else:
            return ""


class AddOnEvent(models.Model):
    """An event to trigger on add-on run"""

    objects = AddOnEventQuerySet.as_manager()

    addon = models.ForeignKey(
        verbose_name=_("add-on"),
        to=AddOn,
        on_delete=models.PROTECT,
        related_name="events",
        help_text=_("The add-on to run"),
    )
    user = models.ForeignKey(
        verbose_name=_("user"),
        to="users.User",
        on_delete=models.PROTECT,
        related_name="events",
        help_text=_("The user who defined this event"),
    )
    parameters = models.JSONField(
        _("parameters"),
        default=dict,
        help_text=_("The user supplied parameters to run the add-on with"),
    )
    event = models.IntegerField(
        _("event"),
        choices=Event.choices,
        help_text=_("The event to trigger the add-on run"),
    )
    scratch = models.JSONField(
        _("scratch"),
        default=dict,
        help_text=_("Field to store data for add-on between events"),
    )

    created_at = AutoCreatedField(
        _("created at"), help_text=_("Timestamp of when the add-on event was created")
    )
    updated_at = AutoLastModifiedField(
        _("updated at"),
        help_text=_("Timestamp of when the add-on event was last updated"),
    )

    def __str__(self):
        return f"Event: {self.addon_id} - {self.event}"

    def dispatch(self):
        """Run the add-on when triggered by this event"""
        # DocumentCloud
        from documentcloud.addons.tasks import dispatch

        with transaction.atomic():
            run = AddOnRun.objects.create(
                addon_id=self.addon_id, event=self, user=self.user, dismissed=True
            )
            transaction.on_commit(
                lambda: dispatch.delay(
                    run.addon_id,
                    run.uuid,
                    self.user_id,
                    [],
                    "",
                    self.parameters,
                    self.id,
                )
            )


class GitHubAccount(models.Model):
    """A linked GitHub account"""

    user = models.ForeignKey(
        verbose_name=_("user"),
        to="users.User",
        on_delete=models.PROTECT,
        null=True,
        related_name="github_accounts",
        help_text=_("The user associated with this GitHub account"),
    )
    name = models.CharField(
        _("name"), max_length=255, help_text=_("The GitHub username")
    )
    uid = models.IntegerField(
        _("uid"), unique=True, help_text=_("The ID for the GitHub account")
    )
    token = models.CharField(
        _("token"), max_length=255, help_text=_("The GitHub token")
    )

    def __str__(self):
        return self.name


class GitHubInstallation(models.Model):
    """An installation of the GitHub app"""

    iid = models.IntegerField(
        _("iid"), unique=True, help_text=_("The ID for the GitHub installation")
    )
    account = models.ForeignKey(
        verbose_name=_("account"),
        to="addons.GitHubAccount",
        on_delete=models.PROTECT,
        related_name="installations",
        help_text=_("The account which installed the app"),
    )
    name = models.CharField(
        _("name"),
        max_length=255,
        help_text=_(
            "The GitHub name of the user or organization the app was installed for"
        ),
    )
    removed = models.BooleanField(
        _("removed"), help_text=_("This installation was removed"), default=False
    )

    def __str__(self):
        return self.name

    @property
    def token(self):
        """Get an access token for this installation"""
        key = f"ghi_token:{self.iid}"
        token = cache.get(key)
        expire_in = 600
        if not token:
            with cache.lock(key):
                token = cache.get(key)
                if not token:
                    now = int(datetime.now().timestamp())
                    payload = {
                        "iat": now - 60,
                        "exp": now + expire_in,
                        "iss": settings.GITHUB_APP_ID,
                    }
                    jwt_token = jwt.encode(
                        payload, settings.GITHUB_APP_PRIVATE_KEY, algorithm="RS256"
                    )
                    headers = {
                        "Accept": "vnd.github.v3+json",
                        "Authorization": f"Bearer {jwt_token}",
                    }
                    resp = requests.post(
                        "https://api.github.com/app/installations/"
                        f"{self.iid}/access_tokens",
                        headers=headers,
                    )
                    resp = resp.json()
                    token = resp["token"]
                    cache.set(key, token, expire_in - 10)
        return token
