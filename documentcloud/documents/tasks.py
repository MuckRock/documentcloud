# Django
from celery.schedules import crontab
from celery.task import periodic_task, task
from django.conf import settings
from django.core.cache import cache
from django.db import transaction

# Standard Library
import logging
import sys

# Third Party
import pysolr
from requests.exceptions import HTTPError, RequestException

# DocumentCloud
from documentcloud.common.environment import httpsub, storage
from documentcloud.documents.choices import Status
from documentcloud.documents.models import Document
from documentcloud.documents.search import SOLR

logger = logging.getLogger(__name__)

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

logger = logging.getLogger(__name__)


@task(autoretry_for=(HTTPError,), retry_backoff=30)
def fetch_file_url(file_url, document_pk):
    """Download a file to S3 when given a URL on document creation"""
    document = Document.objects.get(pk=document_pk)
    try:
        storage.fetch_url(file_url, document.doc_path)
    except RequestException as exc:
        if (
            exc.response
            and exc.response.status_code >= 500
            and fetch_file_url.request.retries < fetch_file_url.max_retries
        ):
            # a 5xx error can be retried - using celery autoretry
            raise

        # log all other request errors and 5xx errors past the max retries
        with transaction.atomic():
            document.errors.create(message=exc.args[0])
            document.status = Status.error
            document.save()
            transaction.on_commit(
                lambda: solr_index.delay(document.pk, field_updates={"status": "set"})
            )
    else:
        document.status = Status.pending
        document.save()
        transaction.on_commit(
            lambda: solr_index.delay(document.pk, field_updates={"status": "set"})
        )
        process.delay(document_pk, document.slug)


@task(
    autoretry_for=(RequestException,), retry_backoff=30, retry_kwargs={"max_retries": 8}
)
def process(document_pk, slug):
    """Start the processing"""
    httpsub.post(
        settings.DOC_PROCESSING_URL,
        json={"doc_id": document_pk, "slug": slug, "method": "process_pdf"},
    )


@task(
    autoretry_for=(RequestException,), retry_backoff=30, retry_kwargs={"max_retries": 8}
)
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


@task(
    autoretry_for=(RequestException,), retry_backoff=30, retry_kwargs={"max_retries": 8}
)
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
    """Update the access settings for all assets for the given document"""
    document = Document.objects.get(pk=document_pk)
    logger.info("update access: %d - %s", document_pk, document.title)
    access = "public" if document.public else "private"
    files = storage.list(document.path)
    for i in range(0, len(files), settings.UPDATE_ACCESS_CHUNK_SIZE):
        logger.info("update access: launching %s", files[i])
        do_update_access.delay(files[i : i + settings.UPDATE_ACCESS_CHUNK_SIZE], access)


@task
def do_update_access(files, access):
    """Update access settings for a single chunk of assets"""
    logger.info("START do update access: %s", files[0])
    storage.async_set_access(files, access)
    logger.info("DONE: do update access: %s", files[0])


@task(autoretry_for=(pysolr.SolrError,), retry_backoff=60)
def solr_index(document_pk, solr_document=None, field_updates=None, index_text=False):
    if solr_document is None:
        try:
            document = Document.objects.get(pk=document_pk)
        except Document.DoesNotExist:
            # if document no longer exists, just skip
            return
        if field_updates:
            solr_document = document.solr(field_updates.keys(), index_text=index_text)
        else:
            solr_document = document.solr(index_text=index_text)

    SOLR.add([solr_document], fieldUpdates=field_updates)

    Document.objects.filter(pk=document_pk).update(solr_dirty=False)


@periodic_task(run_every=crontab(minute=30))
def solr_index_dirty():
    """Task to try and index all dirty models periodically"""
    # acquire a lock to ensure we do not try to run this task multiple times
    # in parallel
    lock = cache.lock("solr_index_dirty")
    if lock.acquire(blocking=False):
        # check to make sure the solr server is responsive before trying to index
        try:
            SOLR.search("*:*")
        except pysolr.SolrError as exc:
            logger.error("Solr is down: %s", exc, exc_info=sys.exc_info())
            return

        # get the deleted documents and delete them from Solr
        deleted = Document.objects.filter(status=Status.deleted)
        deleted_count = deleted.count()
        logger.info("Solr index dirty: %d documents to delete", deleted_count)
        deleted_documents = deleted[: settings.SOLR_DIRTY_LIMIT]
        for document in deleted_documents:
            solr_delete.delay(document.pk)

        # get the dirty documents and index them
        dirty = Document.objects.filter(solr_dirty=True).exclude(status=Status.deleted)
        dirty_count = dirty.count()
        logger.info("Solr index dirty: %d documents to index", dirty_count)
        dirty_documents = dirty[: settings.SOLR_DIRTY_LIMIT]
        for document in dirty_documents:
            logger.info("solr index dirty: reindexing %s", document.pk)
            # only index the full text if the document is in a successful state
            solr_index.delay(document.pk, index_text=document.status == Status.success)

        # if there were more documents than the limit, continue indexing
        # after a delay
        if (
            deleted_count > settings.SOLR_DIRTY_LIMIT
            or dirty_count > settings.SOLR_DIRTY_LIMIT
        ):
            solr_index_dirty.apply_async(countdown=settings.SOLR_DIRTY_COUNTDOWN)
    else:
        logger.info("Solr index dirty failed to acquire the lock")
