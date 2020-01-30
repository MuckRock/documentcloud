# Django
from celery.schedules import crontab
from celery.task import periodic_task, task
from django.conf import settings
from django.db import transaction

# Third Party
import pysolr
from requests.exceptions import HTTPError

# DocumentCloud
from documentcloud.common.environment import httpsub, storage
from documentcloud.documents.choices import Status
from documentcloud.documents.models import Document
from documentcloud.documents.search import SOLR

if settings.ENVIRONMENT.startswith("local"):
    # pylint: disable=unused-import
    from documentcloud.documents.local_tasks import (
        process_file_internal,
        cache_pages,
        extract_images,
        ocr_pages,
        assemble_text,
        redact_document,
    )


@task(autoretry_for=(HTTPError,), retry_backoff=30)
def fetch_file_url(file_url, document_pk):
    """Download a file to S3 when given a URL on document creation"""
    document = Document.objects.get(pk=document_pk)
    try:
        storage.fetch_url(file_url, document.doc_path)
    except HTTPError as exc:
        if (
            exc.response.status_code >= 500
            and fetch_file_url.request.retries < fetch_file_url.max_retries
        ):
            # a 5xx error can be retried - using celery autoretry
            raise

        # log 4xx errors and 5xx errors past the maximum retry
        with transaction.atomic():
            document.errors.create(
                message=f'Fetching file "{file_url}" failed with status code: '
                f"{exc.response.status_code}"
            )
            document.status = Status.error
            document.save()
    else:
        document.status = Status.pending
        document.save()
        httpsub.post(
            settings.DOC_PROCESSING_URL,
            json={
                "doc_id": document_pk,
                "slug": document.slug,
                "method": "process_pdf",
            },
        )


@task
def process(document_pk, slug):
    """Start the processing"""
    httpsub.post(
        settings.DOC_PROCESSING_URL,
        json={"doc_id": document_pk, "slug": slug, "method": "process_pdf"},
    )


@task
def redact(document_pk, slug, redactions):
    """Start the redacting"""
    httpsub.post(
        settings.DOC_PROCESSING_URL,
        json={
            "method": "redact_doc",
            "doc_id": document_pk,
            "slug": slug,
            "redactions": redactions,
        },
    )


@task
def process_cancel(document_pk):
    """Stop the processing"""
    httpsub.post(
        settings.DOC_PROCESSING_URL,
        json={"method": "cancel_doc_processing", "doc_id": document_pk},
    )


@task
def delete_document_files(path):
    # delete files from storage
    storage.delete(path)


@task(autoretry_for=(pysolr.SolrError,), retry_backoff=60)
def solr_delete(document_pk):
    # delete document from solr index
    SOLR.delete(id=document_pk)

    # after succesfully deleting from solr, we can delete the correspodning
    # record from the database
    Document.objects.filter(pk=document_pk).delete()


@task
def update_access(document_pk):
    document = Document.objects.get(pk=document_pk)
    access = "public" if document.public else "private"
    storage.set_access(document.path, access)


@task(
    autoretry_for=(pysolr.SolrError,),
    retry_backoff=60,
    time_limit=settings.CELERY_SLOW_TASK_TIME_LIMIT,
    soft_time_limit=settings.CELERY_SLOW_TASK_SOFT_TIME_LIMIT,
)
def solr_index(document_pk, solr_document=None, field_updates=None, index_text=False):
    if solr_document is None:
        document = Document.objects.get(pk=document_pk)
        if field_updates:
            solr_document = document.solr(field_updates.keys(), index_text=index_text)
        else:
            solr_document = document.solr(index_text=index_text)

    SOLR.add([solr_document], fieldUpdates=field_updates)

    Document.objects.filter(pk=document_pk).update(solr_dirty=False)


@periodic_task(run_every=crontab(hour=1))
def solr_index_dirty():
    """Task to try and index all dirty models once a day"""
    # check to make sure the solr server is responsive before trying to index
    try:
        SOLR.search("*:*")
    except pysolr.SolrError:
        return

    # XXX should we bulk these?
    # XXX check all deleted documents
    # XXX put a limit on these
    for document in Document.objects.filter(solr_dirty=True):
        if document.status == Status.deleted:
            solr_delete.delay(document.pk)
        else:
            solr_index.delay(document.pk)
