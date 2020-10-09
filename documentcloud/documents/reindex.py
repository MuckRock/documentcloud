"""
Re-index all documents to a new Solr collection
"""
# Django
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

# Standard Library
import logging

# Third Party
import pysolr
import requests

# DocumentCloud
from documentcloud.common import path
from documentcloud.common.environment import storage
from documentcloud.documents.choices import Status
from documentcloud.documents.models import DeletedDocument, Document

logger = logging.getLogger(__name__)


class AliasError(Exception):
    """An error occurred while creating the solr alias"""


def get_solr_connection(collection_name):
    """Get a Solr connection to a custom collection name"""
    return pysolr.Solr(
        settings.SOLR_BASE_URL + collection_name,
        auth=settings.SOLR_AUTH,
        search_handler=settings.SOLR_SEARCH_HANDLER,
        verify=settings.SOLR_VERIFY,
    )


def solr_reindex_all(collection_name, after_timestamp=None, delete_timestamp=None):
    """Manage the re-index process"""
    if cache.get("solr_reindex_cancel"):
        logger.info("[SOLR REINDEX] solr_reindex_all cancelled")
        return

    if delete_timestamp is None:
        # check for any document deleted after we start the full re-index
        delete_timestamp = timezone.now()

    documents, before_timestamp = prepare_documents(after_timestamp)
    batch_index(collection_name, documents)
    check_remaining_documents(collection_name, before_timestamp, delete_timestamp)


def prepare_documents(after_timestamp):
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


def batch_index(collection_name, documents):
    """Batch re-index a list of documents"""
    solr = get_solr_connection(collection_name)

    # get the json txt file names for all of the documents
    logger.info("[SOLR REINDEX] get file names...")
    file_names = [path.json_text_path(d.pk, d.slug) for d in documents]
    # download the files in parallel
    logger.info("[SOLR REINDEX] get page text...")
    page_text = storage.async_download(file_names)
    # generate the data to index into solr
    logger.info("[SOLR REINDEX] get solr documents...")
    solr_documents = [d.solr(index_text=p) for d, p in zip(documents, page_text)]

    # We don't want to send too large of a payload to solr at once
    # most documents are well, well under the size limit where it would start to be a
    # problem, but there are a few very large documents.  If the list of documents
    # is too large, we will remove the largest element, index it by itself, and then
    # retry on the remanining documents.  We expect the list being too large
    # to almost always be due to a single very large document rather than
    # to multiple medium-large documents
    while documents_size(solr_documents) > settings.SOLR_REINDEX_MAX_SIZE:
        # if the solr_documents are too large to be batch indexed, remove
        # the largest document
        logger.info(
            "[SOLR REINDEX] document batch too large (%s), removing largest document",
            documents_size(solr_documents),
        )
        large_document, solr_documents = remove_largest_document(solr_documents)
        logger.info(
            "[SOLR REINDEX] removed one document of size %s, rest size %s",
            document_size(large_document),
            documents_size(solr_documents),
        )
        single_index(solr, large_document)

    logger.info("[SOLR REINDEX] solr add")
    solr.add(solr_documents)


def document_size(solr_document):
    """Size of a single solr document"""
    return sum(len(str(v)) for v in solr_document.values())


def documents_size(solr_documents):
    """Sum the fields from all of the given solr documents"""
    # This should be faster than converting the whole thing to json
    return sum(document_size(d) for d in solr_documents)


def remove_largest_document(solr_documents):
    """Remove the single largest document from the list of documents"""
    sizes = [document_size(d) for d in solr_documents]
    large_document = solr_documents.pop(sizes.index(max(sizes)))
    return large_document, solr_documents


def single_index(solr, document):
    """Index a single, large document"""
    logger.info("[SOLR REINDEX] indexing large document %s", document.get("title"))
    if document_size(document) < settings.SOLR_REINDEX_MAX_SIZE:
        # if the document is within the size limit on its own, just index it
        logger.info("[SOLR REINDEX] indexing large document done")
        solr.add([document])
        return

    # first index the non page text fields
    logger.info("[SOLR REINDEX] indexing large document non page fields")
    non_page_document = {
        k: v for k, v in document.items() if not k.startswith("page_no")
    }
    solr.add([non_page_document])

    # now update the pages, staying under the limit
    size = 0
    field_updates = {}
    page_document = {}
    page_fields = {k: v for k, v in document.items() if k.startswith("page_no")}
    logger.info(
        "[SOLR REINDEX] indexing large document page fields: %s", len(page_fields)
    )
    for page_field, page_value in page_fields.items():
        size += len(page_value)
        # if adding the next page would put us over the limit, add the current fields
        # to solr, then start building up a new document
        if size > settings.SOLR_REINDEX_MAX_SIZE:
            logger.info(
                "[SOLR REINDEX] indexing large document pages: %s", len(page_document)
            )
            solr.add([page_document], fieldUpdates=field_updates)
            size = len(page_value)
            field_updates = {}
            page_document = {}

        # continue adding pages to the document to index
        page_document[page_field] = page_value
        field_updates[page_field] = "set"

    # index the remaining pages
    logger.info("[SOLR REINDEX] indexing large document pages: %s", len(page_document))
    solr.add([page_document], fieldUpdates=field_updates)


def check_remaining_documents(collection_name, before_timestamp, delete_timestamp):
    """Check how many documents are remaining and decide it we should continue
    reindexing
    """
    from documentcloud.documents import tasks

    # check how many documents we have left to re-index
    documents_left = (
        Document.objects.exclude(status=Status.deleted)
        .filter(updated_at__gt=before_timestamp)
        .count()
    )
    if (
        documents_left > settings.SOLR_REINDEX_LIMIT
        and (timezone.now() - before_timestamp).total_seconds()
        > settings.SOLR_REINDEX_CATCHUP_SECONDS
    ):
        # if there are many documents left and we are not too close to the current time
        # continue re-indexing
        logger.info("[SOLR REINDEX] continuing with %d documents left", documents_left)
        tasks.solr_reindex_all.delay(
            collection_name, before_timestamp, delete_timestamp
        )
    else:
        logger.info(
            "[SOLR REINDEX] done, re-index all documents updated after %s, "
            "delete all documents after %s",
            before_timestamp,
            delete_timestamp,
        )
        update_alias(collection_name)

        # mark all remaining documents as dirty and begin re-indexing them
        Document.objects.exclude(status=Status.deleted).filter(
            updated_at__gt=before_timestamp
        ).update(solr_dirty=True)
        tasks.solr_index_dirty.delay()

        # delete all documents from the new solr collection that were deleted since
        # we started re-indexing
        for document in DeletedDocument.objects.filter(
            created_at__gte=delete_timestamp
        ):
            tasks.solr_delete.delay(document.pk)


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
