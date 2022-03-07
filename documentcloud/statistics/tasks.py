# Django
from celery.exceptions import SoftTimeLimitExceeded
from celery.schedules import crontab
from celery.task import periodic_task
from django.core.management import call_command
from django.db.models import Sum
from django.db.models.aggregates import Count
from django.db.models.functions import Coalesce
from django.db.models.query_utils import Q

# Standard Library
import logging
from datetime import date, timedelta

# DocumentCloud
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.models import Document, Note
from documentcloud.projects.models import Project
from documentcloud.statistics.models import Statistics

logger = logging.getLogger(__name__)

# This is using UTC time instead of the local timezone
@periodic_task(
    run_every=crontab(hour=5, minute=30), time_limit=3600, soft_time_limit=3600
)
def store_statistics():
    """Store the daily statistics"""
    # pylint: disable=too-many-statements

    logger.info("[STORE STATS] Begin")

    yesterday = date.today() - timedelta(1)

    kwargs = {}
    kwargs["date"] = yesterday

    logger.info("[STORE STATS] Document counts")
    document_counts = Document.objects.aggregate(
        all=Count("pk"),
        public=Count("pk", filter=Q(access=Access.public)),
        private=Count("pk", filter=Q(access=Access.private)),
        organization=Count("pk", filter=Q(access=Access.organization)),
        invisible=Count("pk", filter=Q(access=Access.invisible)),
        success=Count("pk", filter=Q(status=Status.success)),
        readable=Count("pk", filter=Q(status=Status.readable)),
        pending=Count("pk", filter=Q(status=Status.pending)),
        error=Count("pk", filter=Q(status=Status.error)),
        nofile=Count("pk", filter=Q(status=Status.nofile)),
        deleted=Count("pk", filter=Q(status=Status.deleted)),
    )

    kwargs["total_documents"] = document_counts.pop("all")
    for key, value in document_counts.items():
        kwargs[f"total_documents_{key}"] = value

    logger.info("[STORE STATS] Page counts")
    page_counts = Document.objects.aggregate(
        all=Coalesce(Sum("page_count"), 0),
        public=Coalesce(Sum("page_count", filter=Q(access=Access.public)), 0),
        private=Coalesce(Sum("page_count", filter=Q(access=Access.private)), 0),
        organization=Coalesce(
            Sum("page_count", filter=Q(access=Access.organization)), 0
        ),
        invisible=Coalesce(Sum("page_count", filter=Q(access=Access.invisible)), 0),
    )

    kwargs["total_pages"] = page_counts.pop("all")
    for key, value in page_counts.items():
        kwargs[f"total_pages_{key}"] = value

    logger.info("[STORE STATS] Note counts")
    note_counts = Note.objects.aggregate(
        all=Count("pk"),
        public=Count("pk", filter=Q(access=Access.public)),
        private=Count("pk", filter=Q(access=Access.private)),
        organization=Count("pk", filter=Q(access=Access.organization)),
        invisible=Count("pk", filter=Q(access=Access.invisible)),
    )

    kwargs["total_notes"] = note_counts.pop("all")
    for key, value in note_counts.items():
        kwargs[f"total_notes_{key}"] = value

    logger.info("[STORE STATS] User counts")
    user_counts = Document.objects.order_by().aggregate(
        all=Count("user_id", distinct=True),
        public=Count("user_id", distinct=True, filter=Q(access=Access.public)),
        private=Count("user_id", distinct=True, filter=Q(access=Access.private)),
        organization=Count(
            "user_id", distinct=True, filter=Q(access=Access.organization)
        ),
    )
    kwargs["total_users_uploaded"] = user_counts.pop("all")
    for key, value in user_counts.items():
        kwargs[f"total_users_{key}_uploaded"] = value

    logger.info("[STORE STATS] Organization counts")
    org_counts = Document.objects.order_by().aggregate(
        all=Count("organization_id", distinct=True),
        public=Count("organization_id", distinct=True, filter=Q(access=Access.public)),
        private=Count(
            "organization_id", distinct=True, filter=Q(access=Access.private)
        ),
        organization=Count(
            "organization_id", distinct=True, filter=Q(access=Access.organization)
        ),
    )
    kwargs["total_organizations_uploaded"] = org_counts.pop("all")
    for key, value in org_counts.items():
        kwargs[f"total_organizations_{key}_uploaded"] = value

    logger.info("[STORE STATS] Project counts")
    kwargs["total_projects"] = Project.objects.count()

    logger.info("[STORE STATS] Create")
    Statistics.objects.create(**kwargs)
    logger.info("[STORE STATS] Done")


@periodic_task(
    run_every=crontab(hour=6, minute=0), time_limit=1800, soft_time_limit=1740
)
def db_cleanup():
    """Call some management commands to clean up the database"""
    logger.info("Starting DB Clean up")
    try:
        call_command("clearsessions", verbosity=2)
        call_command("deleterevisions", "documents", days=90, verbosity=2)
        call_command(
            "deleterevisions",
            "organizations",
            "addons",
            "projects",
            "statistics",
            "users",
            days=180,
            verbosity=2,
        )
    except SoftTimeLimitExceeded:
        logger.error("DB Clean up took too long")
    logger.info("Ending DB Clean up")
