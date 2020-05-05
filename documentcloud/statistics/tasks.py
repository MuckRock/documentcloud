# Django
from celery.schedules import crontab
from celery.task import periodic_task
from django.db.models import Sum
from django.db.models.functions import Coalesce

# Standard Library
from datetime import date, timedelta

# DocumentCloud
from documentcloud.documents.choices import Access
from documentcloud.documents.models import Document, Note
from documentcloud.projects.models import Project
from documentcloud.statistics.models import Statistics


# This is using UTC time instead of the local timezone
@periodic_task(run_every=crontab(hour=5, minute=30))
def store_statistics():
    """Store the daily statistics"""
    # pylint: disable=too-many-statements

    yesterday = date.today() - timedelta(1)

    kwargs = {}
    kwargs["date"] = yesterday

    kwargs["total_documents"] = Document.objects.count()
    kwargs["total_documents_public"] = Document.objects.filter(
        access=Access.public
    ).count()
    kwargs["total_documents_organization"] = Document.objects.filter(
        access=Access.organization
    ).count()
    kwargs["total_documents_private"] = Document.objects.filter(
        access=Access.private
    ).count()
    kwargs["total_documents_invisible"] = Document.objects.filter(
        access=Access.invisible
    ).count()

    kwargs["total_pages"] = Document.objects.aggregate(
        pages=Coalesce(Sum("page_count"), 0)
    )["pages"]
    kwargs["total_pages_public"] = Document.objects.filter(
        access=Access.public
    ).aggregate(pages=Coalesce(Sum("page_count"), 0))["pages"]
    kwargs["total_pages_organization"] = Document.objects.filter(
        access=Access.organization
    ).aggregate(pages=Coalesce(Sum("page_count"), 0))["pages"]
    kwargs["total_pages_private"] = Document.objects.filter(
        access=Access.private
    ).aggregate(pages=Coalesce(Sum("page_count"), 0))["pages"]
    kwargs["total_pages_invisible"] = Document.objects.filter(
        access=Access.invisible
    ).aggregate(pages=Coalesce(Sum("page_count"), 0))["pages"]

    kwargs["total_notes"] = Note.objects.count()
    kwargs["total_notes_public"] = Note.objects.filter(access=Access.public).count()
    kwargs["total_notes_organization"] = Note.objects.filter(
        access=Access.organization
    ).count()
    kwargs["total_notes_private"] = Note.objects.filter(access=Access.private).count()
    kwargs["total_notes_invisible"] = Note.objects.filter(
        access=Access.invisible
    ).count()

    kwargs["total_projects"] = Project.objects.count()

    Statistics.objects.create(**kwargs)
