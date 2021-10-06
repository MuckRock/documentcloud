"""
Functions to index documents into Solr

There are three basic types of re-indexing:
    * Normal indexing of a document - done one document at a time and just for the
    fields that were updated.

    * Dirty indexing - a document is marked as dirty when it is changed, and clean
    once it is indexed.  If something goes wrong, a periodic task will attempt to
    do a full re-index on all dirty documents, to prevent intermittent errors from
    preventing documents from being indexed correctly.  This is also used when
    importing large amounts of documents into the system.  This is done in batches
    for efficiency.

    * Full re-index - all documents are indexed into a new Solr collection.  Once most
    documents are in the new collection, we switch over to using the new collection
    at which point the old collection can be deleted.  This is done when we need to
    update our indexing options or upgrade to a new version of Solr.  This shares
    batch logic with dirty indexing
"""
# Django
from celery import chord, signature
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

# Standard Library
import json
import logging
import time

# Third Party
import pysolr
import requests
from config import celery_app
from dateutil.parser import parse

# DocumentCloud
from documentcloud.common import path
from documentcloud.common.environment import storage
from documentcloud.core.utils import grouper
from documentcloud.documents.choices import Status
from documentcloud.documents.models import DeletedDocument, Document
from documentcloud.documents.search import SOLR

logger = logging.getLogger(__name__)

# Exceptions


class SolrAdminError(Exception):
    """An error occurred while using the Solr admin API"""


# Utils


def get_solr_connection(collection_name):
    """Get a Solr connection to a custom collection name"""
    if collection_name is None:
        return SOLR

    return pysolr.Solr(
        settings.SOLR_BASE_URL + collection_name,
        auth=settings.SOLR_AUTH,
        search_handler=settings.SOLR_SEARCH_HANDLER,
        verify=settings.SOLR_VERIFY,
    )


def document_size(solr_document):
    """Size of a single solr document"""
    # len("<add><doc></doc></add>") == 22
    # len('<field name=""></field>') == 23
    # Encode the key and value into unicode
    # This gives a close approximation of the length of the XML document to be sent
    # to Solr, but is much faster than doing the actual XML conversion
    return 22 + sum(
        23 + len(str(k).encode("utf8") + str(v).encode("utf8"))
        for k, v in solr_document.items()
    )


def _solr_admin_request(method, url, data, name, retry=0):
    """Helper function to use the Solr admin API"""
    session = requests.Session()
    session.verify = settings.SOLR_VERIFY
    if method == "post":
        # post using json
        kwargs = {"json": data}
    else:
        kwargs = {"data": data}
    response = getattr(session, method)(
        url, auth=(settings.SOLR_USERNAME, settings.SOLR_PASSWORD), **kwargs
    )
    if response.status_code == 200:
        logger.info("[SOLR REINDEX] %s: success", name)
    else:
        logger.error(
            "[SOLR REINDEX] Error %s: %d %s", name, response.status_code, response.text
        )
        if retry < 3:
            time.sleep(0.5)
            _solr_admin_request(method, url, data, name, retry + 1)
        else:
            raise SolrAdminError


def update_alias(collection_name):
    """Point the solr alias to the newly indexed collection"""
    _solr_admin_request(
        "get",
        f"{settings.SOLR_BASE_URL}admin/collections",
        {
            "action": "CREATEALIAS",
            "collections": collection_name,
            "name": settings.SOLR_COLLECTION_NAME,
            "wt": "json",
        },
        "Update Alias",
    )


def _set_commit(collection_name, commit, soft_commit):
    """Set the autoCommit and autoSoftCommit values of the collection"""
    _solr_admin_request(
        "post",
        f"{settings.SOLR_HOST_URL}api/collections/{collection_name}/config",
        {
            "set-property": {
                "updateHandler.autoCommit.maxTime": commit,
                "updateHandler.autoSoftCommit.maxTime": soft_commit,
            }
        },
        "Set commit values",
    )
    _solr_admin_request(
        "get",
        f"{settings.SOLR_BASE_URL}admin/collections",
        {"action": "RELOAD", "name": collection_name, "wt": "json"},
        "Reload config",
    )


def set_commit_indexing(collection_name):
    """Set the commit values for indexing"""
    # hard commit once per minute and disable soft cauto commit
    _set_commit(collection_name, 60000, -1)


def reset_commit(collection_name):
    """Set the commit values for normal usage"""
    # hard commit once per 15 seconds and soft commit once per 2 seconds
    _set_commit(collection_name, 15000, 2000)


# Public functions


def index_single(document_pk, solr_document=None, field_updates=None, index_text=False):
    """Index a single, possibly partial document into Solr

    This is how documents are indexed when they are uploaded or updated
    """
    logger.info(
        "[SOLR INDEX] indexing document %s, fields %s, text %s",
        document_pk,
        field_updates,
        index_text,
    )
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
            # add field updates to avoid clobbering already indexed text
            if not index_text:
                field_updates = {f: "set" for f in solr_document if f != "id"}

    _index_solr_document(SOLR, solr_document, field_updates)

    Document.objects.filter(pk=document_pk).update(solr_dirty=False)


def reindex_single(collection_name, document_pk):
    """Re-index a single document into a new Solr collection

    This is used both for a full re-index into a new collection and for
    indexing dirty solr documents
    """
    logger.info(
        "[SOLR REINDEX] re-indexing document %d into collection %s",
        document_pk,
        collection_name,
    )
    solr = get_solr_connection(collection_name)
    try:
        document = Document.objects.get(pk=document_pk)
    except Document.DoesNotExist:
        # if document no longer exists, just skip
        return

    # only index text if in a succesful state
    solr_document = document.solr(index_text=document.status == Status.success)

    _index_solr_document(solr, solr_document)

    if collection_name is None:
        # if we are indexing into the default collection, clear the dirty flag after
        # a succesful index
        Document.objects.filter(pk=document_pk).update(solr_dirty=False)


def index_batch(document_pks, field_updates):
    """Index a batch of documents with the same field updates

    Does not support indexing text
    """
    logger.info(
        "[SOLR INDEX] indexing documents %s, fields %s", document_pks, field_updates
    )

    documents = Document.objects.filter(pk__in=document_pks)

    solr_documents = [d.solr(field_updates.keys()) for d in documents]
    # no text, groups of 1000 should be well below the size limit
    for group in grouper(solr_documents, 1000):
        group = [g for g in group if g is not None]
        SOLR.add(group, fieldUpdates=field_updates)

    Document.objects.filter(pk__in=document_pks).update(solr_dirty=False)


def reindex_batch(collection_name, document_pks):
    """Re-index a batch of documents into a new Solr collection"""
    # The solr documents for the given documents should be known to be under the
    # size limit before calling this function.  This function will fail otherwise.

    logger.info(
        "[SOLR INDEX] index batch %s collection %s", document_pks, collection_name
    )

    solr = get_solr_connection(collection_name)

    documents = Document.objects.filter(pk__in=document_pks).prefetch_related(
        "projectmembership_set"
    )

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

    if collection_name is None:
        # if we are indexing into the default collection, clear the dirty flag after
        # a succesful index
        Document.objects.filter(pk__in=document_pks).update(solr_dirty=False)


def index_dirty(timestamp=None):
    """Index dirty documents"""

    if timestamp is None:
        # starting a new dirty index process
        timestamp = timezone.now().isoformat()
        status = cache.get_or_set("solr_index_dirty_status", timestamp, timeout=7200)
        if status != timestamp:
            logger.info(
                "[SOLR INDEX] dirty run not starting, already in progress: %s", status
            )
            # a previous run is still running, do not run two in parallel
            return

        # on initial invocation, kick off dirty deletion
        deleted = Document.objects.filter(status=Status.deleted).values_list(
            "pk", flat=True
        )
        deleted_count = deleted.count()
        logger.info("[SOLR DELETE] %d documents to delete", deleted_count)
        for document_pk in deleted:
            celery_app.send_task(
                "documentcloud.documents.tasks.solr_delete", args=[document_pk]
            )

    else:
        # continuing a dirty indexing process, keep the cache alive
        cache.touch("solr_index_dirty_status", timeout=7200)

    status = cache.get("solr_index_dirty_status")
    if status == "cancel":
        # allow for an explicit cancellation of the process
        logger.info("[SOLR INDEX] dirty run cancelled")
        return

    documents = _dirty_prepare_documents()
    tasks = _batch_by_size(None, documents)
    chord(
        tasks,
        signature(
            "documentcloud.documents.tasks.solr_index_dirty_continue",
            args=[timestamp],
            immutable=True,
        ),
    ).delay()


def index_dirty_continue(timestamp):
    """Continue indexing dirty documents if any remaining"""
    # check how many documents we have left to re-index
    documents_left = (
        Document.objects.exclude(status=Status.deleted).filter(solr_dirty=True).count()
    )
    if documents_left > 0:
        # if there are any documents left continue re-indexing
        logger.info(
            "[SOLR INDEX] continuing with %d dirty documents left", documents_left
        )
        celery_app.send_task(
            "documentcloud.documents.tasks.solr_index_dirty", args=[timestamp]
        )
    else:
        logger.info("[SOLR INDEX] done with dirty indexing")
        cache.delete("solr_index_dirty_status")


def reindex_all(collection_name, after_timestamp=None, delete_timestamp=None):
    """Re-index all documents"""
    if cache.get("solr_reindex_cancel"):
        logger.info("[SOLR REINDEX] solr_reindex_all cancelled")
        return

    if delete_timestamp is None:
        # check for any document deleted after we start the full re-index
        delete_timestamp = timezone.now()
        logger.info("[SOLR REINDEX] delete_timestamp %s", delete_timestamp)
        # set the commit values for indexing when we first begin the full re-index
        set_commit_indexing(collection_name)

    documents, before_timestamp = _reindex_prepare_documents(after_timestamp)
    tasks = _batch_by_size(collection_name, documents)
    chord(
        tasks,
        signature(
            "documentcloud.documents.tasks.solr_reindex_continue",
            args=[collection_name, before_timestamp, delete_timestamp],
            immutable=True,
        ),
    ).delay()


def reindex_continue(collection_name, after_timestamp, delete_timestamp):
    """Check how many documents are remaining and decide it we should continue
    reindexing
    """
    # check how many documents we have left to re-index
    documents_left = (
        Document.objects.exclude(status=Status.deleted)
        .filter(updated_at__gt=after_timestamp)
        .count()
    )
    if (
        documents_left > settings.SOLR_INDEX_LIMIT
        and (timezone.now() - parse(after_timestamp)).total_seconds()
        > settings.SOLR_INDEX_CATCHUP_SECONDS
    ):
        # if there are many documents left and we are not too close to the current time
        # continue re-indexing
        logger.info("[SOLR REINDEX] continuing with %d documents left", documents_left)
        celery_app.send_task(
            "documentcloud.documents.tasks.solr_reindex_all",
            args=[collection_name, after_timestamp, delete_timestamp],
        )
    else:
        logger.info(
            "[SOLR REINDEX] done, re-index all documents updated after %s, "
            "delete all documents after %s",
            after_timestamp,
            delete_timestamp,
        )
        # reset the commit values for normal usage before updating the alias
        reset_commit(collection_name)
        update_alias(collection_name)

        # mark all remaining documents as dirty and begin re-indexing them
        Document.objects.exclude(status=Status.deleted).filter(
            updated_at__gt=after_timestamp
        ).update(solr_dirty=True)
        celery_app.send_task("documentcloud.documents.tasks.solr_index_dirty")

        # delete all documents from the new solr collection that were deleted since
        # we started re-indexing
        for document in DeletedDocument.objects.filter(
            created_at__gte=delete_timestamp
        ):
            celery_app.send_task(
                "documentcloud.documents.tasks.solr_delete", args=[document.pk]
            )


# Private functions

## Single indexing


def _index_solr_document(solr, solr_document, field_updates=None):
    """Index a single prepared solr document"""
    document_pk = solr_document["id"]
    logger.info(
        "[SOLR INDEX] indexing document %s - %s - %s - %s - %.200s",
        document_pk,
        solr_document.get("title", ""),
        field_updates,
        solr_document.keys(),
        solr_document,
    )

    # This code assumes that if field_updates is set, the document will
    # be less than the max size - this is because field updates is only set
    # when updating a subset of the metadata fields, and the document
    # should only ever be over the max size when doing a full text index
    if document_size(solr_document) < settings.SOLR_INDEX_MAX_SIZE:
        # if the document is within the size limit on its own, just index it
        solr.add([solr_document], fieldUpdates=field_updates)
        logger.info("[SOLR INDEX] indexing document %s - done", document_pk)
        return

    if field_updates is not None:
        logger.error(
            "[SOLR INDEX] large solr document with field_update set - "
            "document_pk: %s field_updates: %s document_size: %s",
            document_pk,
            field_updates,
            document_size(solr_document),
        )

    # first index the non page text fields
    logger.info("[SOLR INDEX] indexing large document non page fields")
    non_page_document = {
        k: v for k, v in solr_document.items() if not k.startswith("page_no")
    }
    solr.add([non_page_document])

    # now update the pages, staying under the limit
    # size starts at 22 for <add><doc></doc></add>
    size = 22
    field_updates = {}
    page_document = {}
    page_fields = {k: v for k, v in solr_document.items() if k.startswith("page_no")}
    logger.info(
        "[SOLR INDEX] indexing large document %s - page fields: %s",
        document_pk,
        len(page_fields),
    )
    for page_field, page_value in page_fields.items():
        # len('<field name="" update="set"></field>') == 36
        page_size = 36 + len(page_field.encode("utf8")) + len(page_value.encode("utf8"))
        size += page_size
        # if adding the next page would put us over the limit, add the current fields
        # to solr, then start building up a new document
        if size > settings.SOLR_INDEX_MAX_SIZE:
            logger.info(
                "[SOLR INDEX] indexing large document %s - pages: %s",
                document_pk,
                len(page_document),
            )
            solr.add([page_document], fieldUpdates=field_updates)
            # set the size to the initial 22 plus the size of the next page
            size = 22 + page_size
            field_updates = {}
            page_document = {}

        # continue adding pages to the document to index
        page_document[page_field] = page_value[: settings.SOLR_INDEX_MAX_SIZE]
        field_updates[page_field] = "set"

    # index the remaining pages
    logger.info(
        "[SOLR INDEX] indexing large document %s - pages: %s",
        document_pk,
        len(page_document),
    )
    solr.add([page_document], fieldUpdates=field_updates)


## Batch indexing


def _batch_by_size(collection_name, documents):
    """Groups a list of documents into batches which are below the size limit,
    so that they can be sent to Solr together
    """

    file_names = [path.json_text_path(d["pk"], d["slug"]) for d in documents]
    text_sizes = storage.async_size(file_names)

    docs_with_sizes = list(zip(documents, text_sizes))

    docs_with_sizes.sort(key=lambda x: x[1], reverse=True)

    batch = []
    batch_size = 0
    tasks = []
    for document, size in docs_with_sizes:
        if size > settings.SOLR_INDEX_MAX_SIZE:
            # if the isngle document is too large to index at once, index it by itself
            # so it can be indexed in pieces
            logger.info(
                "[SOLR INDEX] batching single document %s size %s", document["pk"], size
            )
            tasks.append(
                signature(
                    "documentcloud.documents.tasks.solr_reindex_single",
                    args=[collection_name, document["pk"]],
                )
            )
        elif (
            batch_size + size > settings.SOLR_INDEX_MAX_SIZE
            or len(batch) >= settings.SOLR_INDEX_BATCH_LIMIT
        ):
            # if adding the next document would make the batch larger than the max
            # size, or if the batch is already at the max size,
            # then send the current batch to be indexed and start a new batch
            logger.info("[SOLR INDEX] batch of %s size %s", batch, batch_size)
            tasks.append(
                signature(
                    "documentcloud.documents.tasks.solr_reindex_batch",
                    args=[collection_name, batch],
                )
            )
            batch = [document["pk"]]
            batch_size = size
        else:
            # otherwise add the current document to the current batch
            batch.append(document["pk"])
            batch_size += size

    logger.info("[SOLR INDEX] batch of %s size %s", batch, batch_size)
    tasks.append(
        signature(
            "documentcloud.documents.tasks.solr_reindex_batch",
            args=[collection_name, batch],
        )
    )
    return tasks


## Re-index all


def _reindex_prepare_documents(after_timestamp):
    """Prepare which documents we will be indexing in this batch"""
    documents = Document.objects.exclude(status=Status.deleted).order_by("updated_at")
    if after_timestamp is None:
        logger.info("[SOLR REINDEX] starting")
    else:
        logger.info("[SOLR REINDEX] continuing after: %s", after_timestamp)
        documents = documents.filter(updated_at__gt=after_timestamp)

    # we want to index about SOLR_INDEX_LIMIT documents at a time per worker
    # grab the timestamp from the document that many documents from the beginning
    # then we will filter for all documents before or equal to that timestamp
    # this ensures we do not miss any documents due to multiple documents
    # with equal updated_at timestamps
    before_timestamp = documents.values_list("updated_at", flat=True)[
        settings.SOLR_INDEX_LIMIT - 1
    ]
    full_count = documents.count()
    documents = documents.filter(updated_at__lte=before_timestamp).values("pk", "slug")
    logger.info(
        "[SOLR REINDEX] reindexing %d documents now, %d documents left to "
        "re-index in total",
        len(list(documents)),
        full_count,
    )
    return documents, before_timestamp


## Dirty indexing


def _dirty_prepare_documents():
    """Prepare which dirty documents will be indexed in this batch"""
    documents = (
        Document.objects.filter(solr_dirty=True)
        .exclude(status=Status.deleted)
        .order_by("-created_at")
    ).values("pk", "slug")

    full_count = documents.count()
    documents = documents[: settings.SOLR_INDEX_LIMIT]
    logger.info(
        "[SOLR INDEX] indexing %d dirty documents now, %d documents left to "
        "re-index in total",
        len(list(documents)),
        full_count,
    )
    return documents
