# Django
from celery import chord
from celery.schedules import crontab
from celery.task import periodic_task, task
from django.conf import settings
from django.db import transaction

# Standard Library
import logging

# Third Party
import pysolr
import redis
from requests.exceptions import HTTPError, RequestException

# DocumentCloud
from documentcloud.common.environment import httpsub, storage
from documentcloud.documents import solr
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.models import Document
from documentcloud.documents.search import SOLR

logger = logging.getLogger(__name__)

if settings.ENVIRONMENT.startswith("local"):
    # pylint: disable=unused-import
    from documentcloud.documents.local_tasks import (
        process_file_internal,
        document_convert,
        cache_pages,
        extract_images,
        ocr_pages,
        assemble_text,
        redact_document,
        start_import_process,
        import_doc,
        finish_import_process,
    )

logger = logging.getLogger(__name__)


@task(autoretry_for=(HTTPError,), retry_backoff=30)
def fetch_file_url(file_url, document_pk, force_ocr):
    """Download a file to S3 when given a URL on document creation"""
    document = Document.objects.get(pk=document_pk)
    try:
        storage.fetch_url(file_url, document.doc_path, document.access)
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
        process.delay(
            document_pk,
            document.slug,
            document.access,
            document.language,
            force_ocr,
            document.original_extension,
        )


@task(
    autoretry_for=(RequestException,), retry_backoff=30, retry_kwargs={"max_retries": 8}
)
def process(document_pk, slug, access, ocr_code, force_ocr, extension="pdf"):
    """Start the processing"""
    httpsub.post(
        settings.DOC_PROCESSING_URL,
        json={
            "doc_id": document_pk,
            "slug": slug,
            "extension": extension,
            "access": access,
            "ocr_code": ocr_code,
            "method": "process_pdf",
            "force_ocr": force_ocr,
        },
    )


@task(
    autoretry_for=(RequestException,), retry_backoff=30, retry_kwargs={"max_retries": 8}
)
def redact(document_pk, slug, access, ocr_code, redactions):
    """Start the redacting"""
    httpsub.post(
        settings.DOC_PROCESSING_URL,
        json={
            "method": "redact_doc",
            "doc_id": document_pk,
            "slug": slug,
            "access": access,
            "ocr_code": ocr_code,
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


# was seeing connection errors - seemed to be an issue with celery or redis
# putting in retries for now to ensure tasks are run
@task(autoretry_for=(redis.exceptions.ConnectionError,))
def update_access(document_pk, status, access):
    """Update the access settings for all assets for the given document"""
    document = Document.objects.get(pk=document_pk)
    logger.info(
        "update access: %d - %s - %d", document_pk, document.title, document.access
    )

    files = storage.list(document.path)
    tasks = []
    for i in range(0, len(files), settings.UPDATE_ACCESS_CHUNK_SIZE):
        tasks.append(
            do_update_access.s(files[i : i + settings.UPDATE_ACCESS_CHUNK_SIZE], access)
        )

    # run all do_update_access tasks in parallel, then run finish_update_access
    # after they have all completed
    chord(tasks, finish_update_access.si(document_pk, status, access)).delay()


@task
def do_update_access(files, access):
    """Update access settings for a single chunk of assets"""
    logger.info("START do update access: %s - %s", files[0], access)
    storage.async_set_access(files, access)
    logger.info("DONE: do update access: %s - %s", files[0], access)


@task
def finish_update_access(document_pk, status, access):
    """Upon finishing an access update, reset the status"""
    logger.info("Finish update access %s %s %s", document_pk, status, access)
    with transaction.atomic():
        field_updates = {"status": "set"}
        kwargs = {}
        if access == Access.public:
            # if we were switching to public, update the access now
            kwargs["access"] = Access.public
            field_updates["access"] = "set"

        Document.objects.filter(pk=document_pk).update(status=status, **kwargs)
        transaction.on_commit(
            lambda: solr_index.delay(document_pk, field_updates=field_updates)
        )


# new solr


@task(autoretry_for=(pysolr.SolrError,), retry_backoff=settings.SOLR_RETRY_BACKOFF)
def solr_index(document_pk, solr_document=None, field_updates=None, index_text=False):
    """Index a single, possibly partial document into Solr"""
    solr.index_single(document_pk, solr_document, field_updates, index_text)


@task(autoretry_for=(pysolr.SolrError,), retry_backoff=settings.SOLR_RETRY_BACKOFF)
def solr_reindex_single(collection_name, document_pk):
    """Re-index a single document into a new Solr collection"""
    solr.reindex_single(collection_name, document_pk)


@task(autoretry_for=(pysolr.SolrError,), retry_backoff=settings.SOLR_RETRY_BACKOFF)
def solr_index_batch(collection_name, document_pks):
    """Re-index a batch of documents into a new Solr collection"""
    solr.index_batch(collection_name, document_pks)


@periodic_task(run_every=crontab(minute=30))
def solr_index_dirty(before_timestamp=None):
    """Index dirty documents"""
    solr.index_dirty(before_timestamp)


@task
def solr_reindex_all(collection_name, after_timestamp=None, delete_timestamp=None):
    """Re-index all documents"""
    solr.reindex_all(collection_name, after_timestamp, delete_timestamp)
