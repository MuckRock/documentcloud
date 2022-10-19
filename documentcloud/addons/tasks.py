# Django
from celery.exceptions import MaxRetriesExceededError
from celery.schedules import crontab
from celery.task import periodic_task, task

# Standard Library
import logging

# Third Party
from requests.exceptions import RequestException

# DocumentCloud
from documentcloud.addons.choices import Event
from documentcloud.addons.models import AddOn, AddOnEvent, AddOnRun
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
        run.save(update_fields=["run_id", "status"])
    else:
        # if we fail to find the run ID, try again
        try:
            find_run_id.retry(
                args=[uuid],
                countdown=min(2**find_run_id.request.retries, 30),
                max_retries=10,
            )
        except MaxRetriesExceededError:
            logger.error("Failed to find run ID: %s", uuid)
            AddOnRun.objects.filter(uuid=uuid).update(status="failure")


@task
def set_run_status(uuid):
    logger.info("[SET RUN STATUS] uuid %s", uuid)
    run = AddOnRun.objects.get(uuid=uuid)
    run.set_status()
    if run.status in ["queued", "in_progress"]:
        # if we are not in a completed status, continue polling for new status
        set_run_status.apply_async(args=[uuid], countdown=5)


@task
def dispatch(addon_id, uuid, user_id, documents, query, parameters, event_id=None):
    # pylint: disable=too-many-arguments
    logger.info("[DISPATCH] uuid %s", uuid)
    addon = AddOn.objects.get(pk=addon_id)
    user = User.objects.get(pk=user_id)

    try:
        addon.dispatch(uuid, user, documents, query, parameters, event_id)
        find_run_id.delay(uuid)
    except RequestException as exc:
        try:
            logger.info("[DISPATCH] retry uuid %s exc %s", uuid, exc)
            dispatch.retry(max_retries=3, countdown=10)
        except MaxRetriesExceededError:
            logger.error("Failed to dispatch: %s", uuid)
            AddOnRun.objects.filter(uuid=uuid).update(status="failure")


@task(
    autoretry_for=(RequestException,), retry_backoff=30, retry_kwargs={"max_retries": 8}
)
def update_config(repository):
    for addon in AddOn.objects.filter(repository=repository, removed=False):
        addon.update_config()


def dispatch_events(event_choice):
    """Run all add-ons for the given event"""
    logger.info("[DISPATCHING EVENTS] type: %s", event_choice)
    events = AddOnEvent.objects.filter(event=event_choice)
    logger.info("[DISPATCHING EVENTS] events to run: %d", len(events))
    for event in events:
        event.dispatch()


@periodic_task(run_every=crontab(minute=0))
def hourly_event():
    dispatch_events(Event.hourly)


@periodic_task(run_every=crontab(minute=30, hour=0))
def daily_event():
    dispatch_events(Event.daily)


@periodic_task(run_every=crontab(minute=30, hour=1, day_of_week=0))
def weekly_event():
    dispatch_events(Event.weekly)
