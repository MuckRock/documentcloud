# Django
from celery import chord
from celery.exceptions import SoftTimeLimitExceeded
from celery.schedules import crontab
from celery.task import periodic_task, task
from django.conf import settings
from django.db import transaction
from django.db.utils import DatabaseError
from django.utils import timezone

# Standard Library
import logging
import sys
from datetime import date

# Third Party
import pysolr
import redis
from requests.exceptions import HTTPError, RequestException

# DocumentCloud
from documentcloud.common.environment import httpsub, storage
from documentcloud.documents import entity_extraction, modifications, solr
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.models import Document, DocumentError
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
        text_position_extract,
        redact_document,
        modify_document,
        start_import_process,
        import_doc,
        finish_import_process,
        retry_errors_local,
    )

logger = logging.getLogger(__name__)


@task(autoretry_for=(HTTPError,), retry_backoff=30)
def fetch_file_url(file_url, document_pk, force_ocr):
    """Download a file to S3 when given a URL on document creation"""
    document = Document.objects.get(pk=document_pk)
    try:
        storage.fetch_url(file_url, document.original_path, document.access)
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


def _httpsub_submit(url, document_pk, json, task_):
    """Helper to reliably submit a task to lambda via HTTP"""
    logger.info(
        "Submitting document %s for %s.  Retry: %d",
        document_pk,
        task_.name,
        task_.request.retries,
    )
    try:
        response = httpsub.post(url, json=json)
        response.raise_for_status()
        logger.info(
            "Submitted document %s for %s succesfully.", document_pk, task_.name
        )
    except RequestException as exc:
        if task_.request.retries >= task_.max_retries:
            with transaction.atomic():
                Document.objects.filter(pk=document_pk).update(status=Status.error)
                transaction.on_commit(
                    lambda: solr_index.delay(
                        document_pk, field_updates={"status": "set"}
                    )
                )
                DocumentError.objects.create(
                    document_id=document_pk,
                    message=f"Submitting for {task_.name} failed",
                )
            logger.error(
                "Submitting document %s for %s failed: %s",
                document_pk,
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
def process(document_pk, slug, access, ocr_code, force_ocr, extension="pdf"):
    """Start the processing"""
    _httpsub_submit(
        settings.DOC_PROCESSING_URL,
        document_pk,
        {
            "doc_id": document_pk,
            "slug": slug,
            "extension": extension,
            "access": access,
            "ocr_code": ocr_code,
            "method": "process_pdf",
            "force_ocr": force_ocr,
        },
        process,
    )


@task(
    autoretry_for=(RequestException,),
    retry_backoff=30,
    retry_kwargs={"max_retries": settings.HTTPSUB_RETRY_LIMIT},
)
def redact(document_pk, slug, access, ocr_code, redactions):
    """Start the redacting"""
    _httpsub_submit(
        settings.DOC_PROCESSING_URL,
        document_pk,
        {
            "method": "redact_doc",
            "doc_id": document_pk,
            "slug": slug,
            "access": access,
            "ocr_code": ocr_code,
            "redactions": redactions,
        },
        redact,
    )


@task(
    autoretry_for=(RequestException,),
    retry_backoff=30,
    retry_kwargs={"max_retries": settings.HTTPSUB_RETRY_LIMIT},
)
def modify(document_pk, page_count, slug, access, modification_data):
    """Start the modification job"""
    _httpsub_submit(
        settings.DOC_PROCESSING_URL,
        document_pk,
        {
            "method": "modify_doc",
            "doc_id": document_pk,
            "page_count": page_count,
            "slug": slug,
            "access": access,
            "modifications": modification_data,
        },
        modify,
    )


@task(
    autoretry_for=(RequestException,),
    retry_backoff=30,
    retry_kwargs={"max_retries": settings.HTTPSUB_RETRY_LIMIT},
)
def process_cancel(document_pk):
    """Stop the processing"""
    _httpsub_submit(
        settings.DOC_PROCESSING_URL,
        document_pk,
        {"method": "cancel_doc_processing", "doc_id": document_pk},
        process_cancel,
    )


@task(autoretry_for=(SoftTimeLimitExceeded,))
def delete_document_files(path):
    """Delete all of the files from storage for the given path"""
    # For AWS, can delete 1000 files at a time - if we hit the time limit,
    # just retry - it will continue deleting files from the path where it left off
    storage.delete(path)


@task(autoretry_for=(pysolr.SolrError,), retry_backoff=60)
def solr_delete(document_pk):
    # delete document from solr index
    SOLR.delete(id=str(document_pk))

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
            # also set the pulbication date
            kwargs["publication_date"] = date.today()

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
def solr_index_batch(document_pks, field_updates):
    """Index a batch of documents with the same field updates"""
    solr.index_batch(document_pks, field_updates)


@task(autoretry_for=(pysolr.SolrError,), retry_backoff=settings.SOLR_RETRY_BACKOFF)
def solr_reindex_batch(collection_name, document_pks):
    """Re-index a batch of documents into a new Solr collection"""
    solr.reindex_batch(collection_name, document_pks)


@periodic_task(run_every=crontab(minute=30))
def solr_index_dirty(timestamp=None):
    """Index dirty documents"""
    solr.index_dirty(timestamp)


@task
def solr_index_dirty_continue(timestamp):
    """Continue indexing dirty documents"""
    solr.index_dirty_continue(timestamp)


@task(
    time_limit=settings.CELERY_SLOW_TASK_TIME_LIMIT,
    soft_time_limit=settings.CELERY_SLOW_TASK_SOFT_TIME_LIMIT,
    autoretry_for=(SoftTimeLimitExceeded,),
    retry_backoff=settings.SOLR_RETRY_BACKOFF,
)
def solr_reindex_all(collection_name, after_timestamp=None, delete_timestamp=None):
    """Re-index all documents"""
    solr.reindex_all(collection_name, after_timestamp, delete_timestamp)


@task
def solr_reindex_continue(collection_name, after_timestamp, delete_timestamp):
    """Continue re-indexing all documents"""
    solr.reindex_continue(collection_name, after_timestamp, delete_timestamp)


# entity extraction


# This could take a while for long documents
@task(soft_time_limit=60 * 30, time_limit=60 * 32)
def extract_entities(document_pk):
    try:
        document = Document.objects.get(pk=document_pk)
    except Document.DoesNotExist:
        return

    entity_extraction.extract_entities(document)


@periodic_task(run_every=600)
@transaction.atomic
def publish_scheduled_documents():
    """Make documents public based on publish_at field"""
    try:
        documents = list(
            Document.objects.filter(
                publish_at__lt=timezone.now(), status=Status.success
            )
            .exclude(access__in=(Access.public, Access.invisible))
            .select_for_update(nowait=True)
        )
    except DatabaseError:
        logger.info("Lock contention for publishign scheduled documents")
        return

    logger.info("Publishing %d scheduled documents", len(documents))
    # mark documents as processing while we update the file access on s3
    Document.objects.filter(pk__in=[d.pk for d in documents]).update(
        status=Status.readable
    )
    for document in documents:
        # update all files to be public
        transaction.on_commit(
            lambda d=document: update_access.delay(d.pk, Status.success, Access.public)
        )
        # update solr
        transaction.on_commit(
            lambda d=document: solr_index.delay(d.pk, field_updates={"status": "set"})
        )


@task
def invalidate_cache(document_pk):
    """Invalidate the CloudFront and CloudFlare caches"""
    document = Document.objects.get(pk=document_pk)
    document.invalidate_cache()
    document.cache_dirty = False
    document.save()


# page modifications


@task
def post_process(document_pk, modification_data):
    document = Document.objects.get(pk=document_pk)
    modifications.post_process(document, modification_data)


# temporary tasks


@task
def solr_add_type():
    """One off task to add `type:document` to all documents in Solr"""
    try:
        docs = SOLR.search("-type:document", rows=200)
        logger.info(
            "[SOLR ADD TYPE] adding type to documents, %d untyped documents found",
            docs.hits,
        )
        if docs.hits == 0:
            logger.info("[SOLR ADD TYPE] finished")
            return
        solr_docs = [{"id": d["id"], "type": "document"} for d in docs]
        SOLR.add(solr_docs, fieldUpdates={"type": "set"})
        # keep calling until we have updated all documents
        # wait in between calls to not overload solr
        solr_add_type.apply_async(countdown=5)
    except Exception as exc:
        # there was an error, try a longer cool off
        logger.info("[SOLR ADD TYPE] Error %s, take a 5 minute break", exc)
        solr_add_type.apply_async(countdown=300)
        raise
