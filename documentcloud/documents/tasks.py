# Django
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
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
from documentcloud.core.choices import Language
from documentcloud.documents import entity_extraction, modifications, solr
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.models import Document, DocumentError
from documentcloud.documents.search import SOLR, SOLR_NOTES

logger = logging.getLogger(__name__)

if settings.ENVIRONMENT.startswith("local"):
    # pylint: disable=unused-import
    # DocumentCloud
    from documentcloud.documents.local_tasks import (
        assemble_text,
        cache_pages,
        document_convert,
        extract_images,
        finish_import_process,
        import_doc,
        modify_document,
        ocr_pages,
        process_file_internal,
        redact_document,
        retry_errors_local,
        start_import_process,
        text_position_extract,
    )


@shared_task(autoretry_for=(HTTPError,), retry_backoff=30)
def fetch_file_url(file_url, document_pk, force_ocr, ocr_engine, auth=None):
    """Download a file to S3 when given a URL on document creation"""
    document = Document.objects.get(pk=document_pk)
    if auth is not None:
        auth = tuple(auth)
    try:
        storage.fetch_url(file_url, document.original_path, document.access, auth)
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
            document.index_on_commit(field_updates={"status": "set"})
    else:
        document.create_revision(document.user.pk, "Initial", copy=True)
        document.status = Status.pending
        document.save()
        document.index_on_commit(field_updates={"status": "set"})
        process.delay(
            document.pk,
            document.user.pk,
            document.organization.pk,
            force_ocr,
            ocr_engine,
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
                document = Document.objects.get(pk=document_pk)
                document.status = Status.error
                document.save()
                document.index_on_commit(field_updates={"status": "Set"})
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


@shared_task(
    autoretry_for=(RequestException,),
    retry_backoff=30,
    retry_kwargs={"max_retries": settings.HTTPSUB_RETRY_LIMIT},
)
def process(document_pk, user_pk, org_pk, force_ocr, ocr_engine):
    """Start the processing"""
    document = Document.objects.get(pk=document_pk)
    _httpsub_submit(
        settings.DOC_PROCESSING_URL,
        document.pk,
        {
            "doc_id": document.pk,
            "slug": document.slug,
            "extension": document.original_extension,
            "access": document.access,
            "ocr_code": Language.get_choice(document.language).ocr_code,
            "method": "process_pdf",
            "user_id": user_pk,
            "org_id": org_pk,
            "force_ocr": force_ocr,
            "ocr_engine": ocr_engine,
        },
        process,
    )
    document.create_revision(user_pk, "Processing")


@shared_task(
    autoretry_for=(RequestException,),
    retry_backoff=30,
    retry_kwargs={"max_retries": settings.HTTPSUB_RETRY_LIMIT},
)
def redact(document_pk, user_pk, redactions):
    """Start the redacting"""
    document = Document.objects.get(pk=document_pk)
    _httpsub_submit(
        settings.DOC_PROCESSING_URL,
        document_pk,
        {
            "method": "redact_doc",
            "doc_id": document_pk,
            "slug": document.slug,
            "access": document.access,
            "ocr_code": Language.get_choice(document.language).ocr_code,
            "redactions": redactions,
        },
        redact,
    )
    document.create_revision(user_pk, "Redacting")


@shared_task(
    autoretry_for=(RequestException,),
    retry_backoff=30,
    retry_kwargs={"max_retries": settings.HTTPSUB_RETRY_LIMIT},
)
def modify(document_pk, user_pk, modification_data):
    """Start the modification job"""
    document = Document.objects.get(pk=document_pk)
    _httpsub_submit(
        settings.DOC_PROCESSING_URL,
        document_pk,
        {
            "method": "modify_doc",
            "doc_id": document_pk,
            "page_count": document.page_count,
            "slug": document.slug,
            "access": document.access,
            "modifications": modification_data,
        },
        modify,
    )
    document.create_revision(user_pk, "Modifying")


@shared_task(
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


@shared_task(autoretry_for=(SoftTimeLimitExceeded,))
def delete_document_files(path):
    """Delete all of the files from storage for the given path"""
    # For AWS, can delete 1000 files at a time - if we hit the time limit,
    # just retry - it will continue deleting files from the path where it left off
    storage.delete(path)


@shared_task(
    autoretry_for=(pysolr.SolrError,), retry_backoff=settings.SOLR_RETRY_BACKOFF
)
def solr_delete(document_pk):
    # delete document from solr index
    SOLR.delete(id=str(document_pk))
    # delete the notes
    SOLR_NOTES.delete(q=f"document_s:{document_pk}")

    # after succesfully deleting from solr, we can delete the correspodning
    # record from the database
    Document.objects.filter(pk=document_pk).delete()


# was seeing connection errors - seemed to be an issue with celery or redis
# putting in retries for now to ensure tasks are run
@shared_task(autoretry_for=(redis.exceptions.ConnectionError,))
def update_access(document_pk, status, access, marker=None):
    """Update the access settings for all assets for the given document"""
    document = Document.objects.get(pk=document_pk)
    logger.info(
        "[UPDATE ACCESS]: %d - %s - %d", document_pk, document.title, document.access
    )

    files = storage.list(document.path, marker, limit=settings.UPDATE_ACCESS_CHUNK_SIZE)
    # do not ever make revision PDFs public
    revision_prefix = f"{document.path}revisions/"
    update_files = [f for f in files if not f.startswith(revision_prefix)]
    storage.async_set_access(update_files, access)

    if len(files) == settings.UPDATE_ACCESS_CHUNK_SIZE:
        # there may be more files left, re-run, starting where we left off
        logger.info("[UPDATE ACCESS] start: %s - %s", files[0], access)
        update_access.delay(document_pk, status, access, files[-1])
        logger.info("[UPDATE ACCESS] done:  %s - %s", files[0], access)
    else:
        # we are done
        logger.info("[UPDATE ACCESS] finish %s %s %s", document_pk, status, access)
        with transaction.atomic():
            field_updates = {"status": "set"}
            kwargs = {}
            if access == Access.public:
                # if we were switching to public, update the access now
                kwargs["access"] = Access.public
                field_updates["access"] = "set"
                # also set the publication date
                kwargs["publication_date"] = date.today()

            # update the document status and re-index into solr
            Document.objects.filter(pk=document_pk).update(status=status, **kwargs)
            document.index_on_commit(field_updates=field_updates)


@shared_task
def set_page_text(document_pk, page_text_infos):
    """Update the text information for a document"""
    # pylint: disable=broad-except
    document = Document.objects.get(pk=document_pk)
    logger.info("[SET PAGE TEXT] %d - setting status to readable", document_pk)
    with transaction.atomic():
        document.status = Status.readable
        document.save()
        document.index_on_commit(field_updates={"status": "set"})
    kwargs = {"field_updates": {}}
    try:
        json_text = document.set_page_text(page_text_infos)
    except Exception as exc:
        logger.exception(
            "[SET PAGE TEXT] %d - exception: %s", document_pk, exc, exc_info=exc
        )
    else:
        field_updates = {f"page_no_{i['page_number']}": "set" for i in page_text_infos}
        kwargs = {"field_updates": field_updates, "index_text": json_text}
    finally:
        with transaction.atomic():
            logger.info("[SET PAGE TEXT] %d - setting status to success", document_pk)
            document.status = Status.success
            document.save()
            kwargs["field_updates"]["status"] = "set"
            document.index_on_commit(**kwargs)


# new solr


@shared_task(
    autoretry_for=(pysolr.SolrError,), retry_backoff=settings.SOLR_RETRY_BACKOFF
)
def solr_index(document_pk, solr_document=None, field_updates=None, index_text=False):
    """Index a single, possibly partial document into Solr"""
    solr.index_single(document_pk, solr_document, field_updates, index_text)


@shared_task(
    autoretry_for=(pysolr.SolrError,), retry_backoff=settings.SOLR_RETRY_BACKOFF
)
def solr_reindex_single(collection_name, document_pk):
    """Re-index a single document into a new Solr collection"""
    solr.reindex_single(collection_name, document_pk)


@shared_task(
    autoretry_for=(pysolr.SolrError,), retry_backoff=settings.SOLR_RETRY_BACKOFF
)
def solr_index_batch(document_pks, field_updates):
    """Index a batch of documents with the same field updates"""
    solr.index_batch(document_pks, field_updates)


@shared_task(
    autoretry_for=(pysolr.SolrError,), retry_backoff=settings.SOLR_RETRY_BACKOFF
)
def solr_reindex_batch(collection_name, document_pks):
    """Re-index a batch of documents into a new Solr collection"""
    solr.reindex_batch(collection_name, document_pks)


@shared_task
def solr_index_dirty(timestamp=None):
    """Index dirty documents"""
    solr.index_dirty(timestamp)


@shared_task
def solr_index_dirty_continue(timestamp):
    """Continue indexing dirty documents"""
    solr.index_dirty_continue(timestamp)


@shared_task(
    time_limit=settings.CELERY_SLOW_TASK_TIME_LIMIT,
    soft_time_limit=settings.CELERY_SLOW_TASK_SOFT_TIME_LIMIT,
    autoretry_for=(SoftTimeLimitExceeded,),
    retry_backoff=settings.SOLR_RETRY_BACKOFF,
)
def solr_reindex_all(collection_name, after_timestamp=None, delete_timestamp=None):
    """Re-index all documents"""
    solr.reindex_all(collection_name, after_timestamp, delete_timestamp)


@shared_task
def solr_reindex_continue(collection_name, after_timestamp, delete_timestamp):
    """Continue re-indexing all documents"""
    solr.reindex_continue(collection_name, after_timestamp, delete_timestamp)


# entity extraction


# This could take a while for long documents
@shared_task(soft_time_limit=60 * 30, time_limit=60 * 32)
def extract_entities(document_pk):
    try:
        document = Document.objects.get(pk=document_pk)
    except Document.DoesNotExist:
        return

    entity_extraction.extract_entities(document)


@shared_task
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
        document.index_on_commit(field_updates={"status": "set"})


@shared_task
def invalidate_cache(document_pk):
    """Invalidate the CloudFront and CloudFlare caches"""
    document = Document.objects.get(pk=document_pk)
    document.invalidate_cache()
    document.cache_dirty = False
    document.save()


# page modifications


@shared_task
def post_process(document_pk, modification_data):
    document = Document.objects.get(pk=document_pk)
    modifications.post_process(document, modification_data)


# notes


@shared_task(
    autoretry_for=(pysolr.SolrError,), retry_backoff=settings.SOLR_RETRY_BACKOFF
)
def solr_index_note(note_pk):
    solr.index_note(note_pk)


@shared_task(
    autoretry_for=(pysolr.SolrError,), retry_backoff=settings.SOLR_RETRY_BACKOFF
)
def solr_delete_note(note_pk):
    # delete document from solr index
    SOLR_NOTES.delete(id=str(note_pk))


@shared_task(
    autoretry_for=(pysolr.SolrError,), retry_backoff=settings.SOLR_RETRY_BACKOFF
)
def solr_batch_notes(collection_name, note_pks):
    """Re-index a batch of notes into a new Solr collection"""
    solr.batch_notes(collection_name, note_pks)


# temporary tasks
