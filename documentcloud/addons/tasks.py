# Django
from celery.exceptions import MaxRetriesExceededError
from celery.schedules import crontab
from celery.task import periodic_task, task
from django.db.models.expressions import F
from django.db.models.query_utils import Q
from django.utils import timezone

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
                countdown=2**find_run_id.request.retries,
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


@task
def cancel(uuid):
    logger.info("[CANCEL] uuid %s", uuid)
    run = AddOnRun.objects.get(uuid=uuid)
    result = run.cancel()
    logger.info("[CANCEL] uuid %s result %s", uuid, result)
    if result == "retry":
        cancel.retry(
            args=[uuid],
            countdown=min(2**cancel.request.retries, 30),
            max_retries=10,
        )


@task(
    autoretry_for=(RequestException,), retry_backoff=30, retry_kwargs={"max_retries": 8}
)
def update_config(repository):
    for addon in AddOn.objects.filter(repository=repository, removed=False):
        addon.update_config()


@periodic_task(run_every=crontab(minute="*/5"))
def dispatch_events():
    """Run scheduled add-ons"""
    # get current time - minute should be disvisible by 5 due to crontab,
    # but round to previous 5 minute mark in case their is significant lag for some
    # reason
    now = timezone.now()
    now.replace(minute=now.minute - (now.minute % 5), second=0, microsecond=0)
    # hourly - 12 5-minute buckets
    # daily - 288 5-minute buckets
    # weekly - 2016 5-minute buckets
    hourly_bucket = now.minute / 5
    daily_bucket = (now.minute / 5) + (12 * now.hour)
    weekly_bucket = (now.minute / 5) + (12 * now.hour) + (288 * now.weekday())
    logger.info(
        "[DISPATCHING EVENTS] rounded time: %s hourly: %s daily: %s weekly: %s",
        now,
        hourly_bucket,
        daily_bucket,
        weekly_bucket,
    )
    events = AddOnEvent.objects.annotate(
        hourly_bucket=F("id") % 12,
        daily_bucket=F("id") % 288,
        weekly_bucket=F("id") % 2016,
    ).filter(
        Q(event=Event.hourly, hourly_bucket=hourly_bucket)
        | Q(event=Event.daily, daily_bucket=daily_bucket)
        | Q(event=Event.weekly, weekly_bucket=weekly_bucket)
    )
    logger.info("[DISPATCHING EVENTS] events to run: %d", len(events))
    for event in events:
        event.dispatch()
