# Django
from celery.exceptions import MaxRetriesExceededError
from celery.task import task

# Standard Library
import logging

# Third Party
from requests.exceptions import RequestException

# DocumentCloud
from documentcloud.addons.models import AddOn, AddOnRun
from documentcloud.users.models import User

logger = logging.getLogger(__name__)


@task(
    autoretry_for=(RequestException,),
    retry_backoff=30,
    retry_kwargs={"max_retries": 10},
)
def find_run_id(uuid):
    """Find the GitHub Actions run ID from the AddOnRun's UUID"""
    logger.info("[FIND RUN ID] uuid %s", uuid)
    run = AddOnRun.objects.get(uuid=uuid)
    data = run.find_run_id()

    if data is not None:
        run_id, status, conclusion = data
        run.run_id = run_id
        if status == "completed":
            run.status = conclusion
        else:
            run.status = status
            set_run_status.apply_async(args=[uuid], countdown=5)
        run.save()
    else:
        # if we fail to find the run ID, try again
        find_run_id.retry(
            args=[uuid],
            countdown=min(2 ** find_run_id.request.retries, 30),
            max_retries=10,
        )


@task
def set_run_status(uuid):
    logger.info("[SET RUN STATUS] uuid %s", uuid)
    run = AddOnRun.objects.get(uuid=uuid)
    run.set_status()
    if run.status in ["queued", "in_progress"]:
        # if we are not in a completed status, continue polling for new status
        set_run_status.apply_async(args=[uuid], countdown=5)


@task
def dispatch(addon_id, uuid, user_id, documents, query, parameters):
    addon = AddOn.objects.get(pk=addon_id)
    user = User.objects.get(pk=user_id)

    try:
        addon.dispatch(uuid, user, documents, query, parameters)
        find_run_id.delay(uuid)
    except RequestException as exc:
        try:
            dispatch.retry(exc=exc, max_retries=3, countdown=10)
        except MaxRetriesExceededError:
            logger.error("Failed to dispatch: %s", uuid)
            AddOnRun.objects.filter(uuid=uuid).update(status="failure")


@task(
    autoretry_for=(RequestException,), retry_backoff=30, retry_kwargs={"max_retries": 8}
)
def update_config(repository):
    for addon in AddOn.objects.filter(repository=repository):
        addon.update_config()
