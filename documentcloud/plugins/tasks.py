# Django
from celery.task import task

# Standard Library
import logging

# DocumentCloud
from documentcloud.plugins.models import PluginRun

logger = logging.getLogger(__name__)


@task(retry_kwargs={"max_retries": 10})
def find_run_id(uuid):
    """Find the GitHub Actions run ID from the PluginRun's UUID"""
    logger.info("[FIND RUN ID] uuid %s", uuid)
    run = PluginRun.objects.get(uuid=uuid)
    run_id = run.find_run_id()

    if run_id is not None:
        run.run_id = run_id
        run.status = run.get_status()
        run.save()
    else:
        # if we fail to find the run ID, try again
        find_run_id.retry(args=[uuid], countdown=5)