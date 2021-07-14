# Django
from celery.task import task
from django.conf import settings

# Standard Library
import logging
import sys

# Third Party
from requests.exceptions import RequestException

# DocumentCloud
from documentcloud.common.environment import httpsub
from documentcloud.sidekick.choices import Status
from documentcloud.sidekick.models import Sidekick

logger = logging.getLogger(__name__)

if settings.ENVIRONMENT.startswith("local"):
    # pylint: disable=unused-import
    from documentcloud.sidekick.local_tasks import sidekick_preprocess


def _httpsub_submit(url, project_pk, json, task_):
    """Helper to reliably submit a task to lambda via HTTP"""
    logger.info(
        "Submitting project %s for %s.  Retry: %d",
        project_pk,
        task_.name,
        task_.request.retries,
    )
    try:
        response = httpsub.post(url, json=json)
        response.raise_for_status()
        logger.info("Submitted project %s for %s succesfully.", project_pk, task_.name)
    except RequestException as exc:
        if task_.request.retries >= task_.max_retries:
            Sidekick.objects.filter(project_id=project_pk).update(status=Status.error)
            logger.error(
                "Submitting project %s for %s failed: %s",
                project_pk,
                task_.name,
                exc,
                exc_info=sys.exc_info(),
            )
        else:
            raise


@task(
    autoretry_for=(RequestException,),
    retry_backoff=30,
    retry_kwargs={"max_retries": settings.HTTPSUB_RETRY_LIMIT},
)
def preprocess(project_pk):
    """Start the sidekick pre-processing"""
    _httpsub_submit(
        settings.SIDEKICK_PROCESSING_URL,
        project_pk,
        {"project_id": project_pk},
        preprocess,
    )
