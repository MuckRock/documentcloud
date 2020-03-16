"""Celery tasks for squarelet app"""
# Django
from celery.task import task
from django.conf import settings

# Standard Library
import logging
import sys

# Third Party
import requests

# DocumentCloud
from documentcloud.organizations.models import Organization
from documentcloud.squarelet.utils import squarelet_get
from documentcloud.users.models import User

logger = logging.getLogger(__name__)


@task(name="documentcloud.squarelet.tasks.pull_data")
def pull_data(type_, uuid, **kwargs):
    """Task to pull data from squarelet"""
    types_url = {"user": "users", "organization": "organizations"}
    types_model = {"user": User, "organization": Organization}
    if type_ not in types_url:
        logger.warning("Pull data received invalid type: %s", type_)
        return

    model = types_model[type_]
    if (
        settings.DISABLE_SQUARELET_CREATE
        and not model.objects.filter(uuid=uuid).exists()
    ):
        # if we have disabled creating new instances from squarelet
        # do not try to pull the data unless the instance already exists locally
        return

    try:
        resp = squarelet_get("/api/{}/{}/".format(types_url[type_], uuid))
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.warning("Exception during pull data: %s", exc, exc_info=sys.exc_info())
        pull_data.retry(
            args=(type_, uuid),
            kwargs=kwargs,
            exc=exc,
            countdown=2 ** pull_data.request.retries,
        )
    else:
        data = resp.json()
        logger.info("Pull data for: %s %s %s", type_, uuid, data)
        model.objects.squarelet_update_or_create(uuid, data)
