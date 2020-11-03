"""
Functions to index documents into Solr
"""
# Django
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

# Standard Library
import json
import logging

# Third Party
import pysolr
import requests
from config import celery_app

# DocumentCloud
from documentcloud.common import path
from documentcloud.common.environment import storage
from documentcloud.documents.choices import Status
from documentcloud.documents.models import DeletedDocument, Document
from documentcloud.documents.search import SOLR

logger = logging.getLogger(__name__)

# Exceptions


class AliasError(Exception):
    """An error occurred while creating the solr alias"""


# Utils


def get_solr_connection(collection_name):
    """Get a Solr connection to a custom collection name"""
    return pysolr.Solr(
        settings.SOLR_BASE_URL + collection_name,
        auth=settings.SOLR_AUTH,
        search_handler=settings.SOLR_SEARCH_HANDLER,
        verify=settings.SOLR_VERIFY,
    )


def document_size(solr_document):
    """Size of a single solr document"""
    return sum(len(str(v)) for v in solr_document.values())


def update_alias(collection_name):
    """Point the solr alias to the newly indexed collection"""
    session = requests.Session()
    session.verify = settings.SOLR_VERIFY
    response = session.get(
        f"{settings.SOLR_BASE_URL}admin/collections",
        data={
            "action": "CREATEALIAS",
            "collections": collection_name,
            "name": settings.SOLR_COLLECTION_NAME,
            "wt": "json",
        },
        auth=(settings.SOLR_USERNAME, settings.SOLR_PASSWORD),
    )
    if response.status_code != 200:
        logger.error(
            "[SOLR REINDEX] Error creating solr alias: %d %s",
            response.status_code,
            response.content,
        )
        raise AliasError


# Public functions


def index_single(document_pk, solr_document=None, field_updates=None, index_text=False):
    """Index a single, possibly partial document into Solr"""
    logger.info(
        "[SOLR INDEX] indexing document %d, fields %s, text %s",
        document_pk,
        field_updates,
        index_text,
    )
    if field_updates is not None and "data" in field_updates:
        # update all fields if data was updated to ensure we remove any data keys
        # from solr which were removed from the document
        field_updates = None

    if solr_document is None:
        try:
            document = Document.objects.get(pk=document_pk)
        except Document.DoesNotExist:
            # if document no longer exists, just skip
            return

        if field_updates:
            solr_document = document.solr(field_updates.keys())
        else:
            solr_document = document.solr(index_text=index_text)

    _index_solr_document(SOLR, solr_document)

    Document.objects.filter(pk=document_pk).update(solr_dirty=False)


def reindex_single(collection_name, document_pk):
    """Re-index a single document into a new Solr collection"""
    logger.info("[SOLR INDEX] re-indexing document %d", document_pk)
    solr = get_solr_connection(collection_name)
    try:
        document = Document.objects.get(pk=document_pk)
    except Document.DoesNotExist:
        # if document no longer exists, just skip
        return

    # only index text if in a succesful state
    solr_document = document.solr(index_text=document.status == Status.success)

    _index_solr_document(solr, solr_document)


def index_batch(collection_name, document_pks):
    """Re-index a batch of documents into a new Solr collection"""

    logger.info("[SOLR INDEX] index batch %s", document_pks)

    solr = get_solr_connection(collection_name)
    documents = Document.objects.get(pk__in=document_pks)
    # XXX preload projects here

    # get the json txt file names for all of the documents
    file_names = [path.json_text_path(d.pk, d.slug) for d in documents]
    # download the files in parallel
    page_texts_ = storage.async_download(file_names)

    page_texts = []
    for text in page_texts_:
        try:
            page_texts.append(json.loads(text.decode("utf8")))
        except ValueError:
            page_texts.append({"pages": [], "updated": None})

    # generate the data to index into solr
    solr_documents = [d.solr(index_text=p) for d, p in zip(documents, page_texts)]
    solr.add(solr_documents)


def index_dirty(before_timestamp=None):
    """Index dirty documents"""
    documents, after_timestamp = _dirty_prepare_documents(before_timestamp)
    _batch_by_size(settings.SOLR_COLLECTION_NAME, documents)
    _dirty_check_remaining(after_timestamp)

    if before_timestamp is None:
        # on initial invocation, kick off dirty deletion
        deleted = Document.objects.filter(status=Status.deleted).only("pk")
        deleted_count = deleted.count()
        logger.info("Solr index dirty: %d documents to delete", deleted_count)
        for document in deleted:
            solr_delete.delay(document.pk)


def reindex_all(collection_name, after_timestamp=None, delete_timestamp=None):
    """Re-index all documents"""
    if cache.get("solr_reindex_cancel"):
        logger.info("[SOLR REINDEX] solr_reindex_all cancelled")
        return

    if delete_timestamp is None:
        # check for any document deleted after we start the full re-index
        delete_timestamp = timezone.now()

    documents, before_timestamp = _reindex_prepare_documents(after_timestamp)
    _batch_by_size(collection_name, documents)
    _reindex_check_remaining(collection_name, before_timestamp, delete_timestamp)


# Private functions

## Single indexing


def _index_solr_document(solr, solr_document):
    """Index a single prepared solr document"""
    # XXX rename
    document_pk = solr_document["id"]
    logger.info(
        "[SOLR INDEX] indexing document %s - %s",
        document_pk,
        solr_document.get("title", ""),
    )

    if document_size(solr_document) < settings.SOLR_REINDEX_MAX_SIZE:
        # if the document is within the size limit on its own, just index it
        solr.add([solr_document])
        logger.info("[SOLR REINDEX] indexing document %s - done", document_pk)
        return

    # first index the non page text fields
    logger.info("[SOLR REINDEX] indexing large document non page fields")
    non_page_document = {
        k: v for k, v in solr_document.items() if not k.startswith("page_no")
    }
    solr.add([non_page_document])

    # now update the pages, staying under the limit
    size = 0
    field_updates = {}
    page_document = {}
    page_fields = {k: v for k, v in solr_document.items() if k.startswith("page_no")}
    logger.info(
        "[SOLR REINDEX] indexing large document %s - page fields: %s",
        document_pk,
        len(page_fields),
    )
    for page_field, page_value in page_fields.items():
        size += len(page_value)
        # if adding the next page would put us over the limit, add the current fields
        # to solr, then start building up a new document
        if size > settings.SOLR_REINDEX_MAX_SIZE:
            logger.info(
                "[SOLR REINDEX] indexing large document %s - pages: %s",
                document_pk,
                len(page_document),
            )
            solr.add([page_document], fieldUpdates=field_updates)
            size = len(page_value)
            field_updates = {}
            page_document = {}

        # continue adding pages to the document to index
        page_document[page_field] = page_value[: settings.SOLR_REINDEX_MAX_SIZE]
        field_updates[page_field] = "set"

    # index the remaining pages
    logger.info(
        "[SOLR REINDEX] indexing large document %s - pages: %s",
        document_pk,
        len(page_document),
    )
    solr.add([page_document], fieldUpdates=field_updates)


## Batch indexing


def _batch_by_size(collection_name, documents):
    """Batch re-index a list of documents"""

    # XXX only load pk, slug for documents

    file_names = [path.json_text_path(d.pk, d.slug) for d in documents]
    text_sizes = storage.async_size(file_names)

    docs_with_sizes = zip(documents, text_sizes)

    docs_with_sizes.sort(key=lambda x: x[1], reverse=True)

    batch = []
    batch_size = 0
    for document, size in docs_with_sizes:
        if size > settings.SOLR_INDEX_MAX_SIZE:
            celery_app.send_task(
                "solr_reindex_single", args=[collection_name, document.pk]
            )
        elif batch_size + size > settings.SOLR_INDEX_MAX_SIZE:
            celery_app.send_task("solr_index_batch", args=[collection_name, batch])
            batch = [document.pk]
            batch_size = size
        else:
            batch.append(document.pk)
            batch_size += size

    celery_app.send_task("index_batch", args=[collection_name, batch])


## Re-index all


def _reindex_prepare_documents(after_timestamp):
    """Prepare which documents we will be indexing in this batch"""
    documents = Document.objects.exclude(status=Status.deleted).order_by("updated_at")
    if after_timestamp is None:
        logger.info("[SOLR REINDEX] starting")
    else:
        logger.info("[SOLR REINDEX] continuing after: %s", after_timestamp)
        documents = documents.filter(updated_at__gt=after_timestamp)

    # we want to index about SOLR_REINDEX_LIMIT documents at a time per worker
    # grab the timestamp from the document that many documents from the beginning
    # then we will filter for all documents before or equal to that timestamp
    # this ensures we do not miss any documents due to multiple documents
    # with equal updated_at timestamps
    before_timestamp = documents.values_list("updated_at", flat=True)[
        settings.SOLR_REINDEX_LIMIT - 1
    ]
    full_count = documents.count()
    documents = documents.filter(updated_at__lte=before_timestamp).prefetch_related(
        "projectmembership_set"
    )
    logger.info(
        "[SOLR REINDEX] reindexing %d documents now, %d documents left to "
        "re-index in total",
        len(list(documents)),
        full_count,
    )
    return documents, before_timestamp


def _reindex_check_remaining(collection_name, after_timestamp, delete_timestamp):
    """Check how many documents are remaining and decide it we should continue
    reindexing
    """
    from documentcloud.documents import tasks

    # check how many documents we have left to re-index
    documents_left = (
        Document.objects.exclude(status=Status.deleted)
        .filter(updated_at__gt=after_timestamp)
        .count()
    )
    if (
        documents_left > settings.SOLR_REINDEX_LIMIT
        and (timezone.now() - after_timestamp).total_seconds()
        > settings.SOLR_REINDEX_CATCHUP_SECONDS
    ):
        # if there are many documents left and we are not too close to the current time
        # continue re-indexing
        logger.info("[SOLR REINDEX] continuing with %d documents left", documents_left)
        tasks.solr_reindex_all.delay(collection_name, after_timestamp, delete_timestamp)
    else:
        logger.info(
            "[SOLR REINDEX] done, re-index all documents updated after %s, "
            "delete all documents after %s",
            after_timestamp,
            delete_timestamp,
        )
        update_alias(collection_name)

        # mark all remaining documents as dirty and begin re-indexing them
        Document.objects.exclude(status=Status.deleted).filter(
            updated_at__gt=after_timestamp
        ).update(solr_dirty=True)
        tasks.solr_index_dirty.delay()

        # delete all documents from the new solr collection that were deleted since
        # we started re-indexing
        for document in DeletedDocument.objects.filter(
            created_at__gte=delete_timestamp
        ):
            tasks.solr_delete.delay(document.pk)


## Dirty indexing


def _dirty_prepare_documents(before_timestamp):
    """Prepare which dirty documents will be indexed in this batch"""
    documents = (
        Document.objects.filter(solr_dirty=True)
        .exclude(status=Status.deleted)
        .order_by("-created_at")
    )
    if before_timestamp:
        documents = documents.filter(updated_at__lt=before_timestamp)

    # we want to index about SOLR_REINDEX_LIMIT documents at a time per worker
    # grab the timestamp from the document that many documents from the beginning
    # then we will filter for all documents before or equal to that timestamp
    # this ensures we do not miss any documents due to multiple documents
    # with equal updated_at timestamps
    after_timestamp = documents.values_list("created_at", flat=True)[
        settings.SOLR_REINDEX_LIMIT - 1
    ]
    full_count = documents.count()
    documents = documents.filter(updated_at__gte=after_timestamp).prefetch_related(
        "projectmembership_set"
    )
    logger.info(
        "[SOLR REINDEX] reindexing %d dirty documents now, %d documents left to "
        "re-index in total",
        len(list(documents)),
        full_count,
    )
    return documents, after_timestamp


def _dirty_check_remaining(before_timestamp):
    """Continue indexing dirty documents if any remaining"""
    # check how many documents we have left to re-index
    documents_left = (
        Document.objects.exclude(status=Status.deleted)
        .filter(updated_at__lt=before_timestamp)
        .count()
    )
    if documents_left > 0:
        # if there are any documents left continue re-indexing
        logger.info("[SOLR REINDEX] continuing with %d documents left", documents_left)
        celery_app.send_task("index_dirty", args=[before_timestamp])
