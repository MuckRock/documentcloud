# Django
from celery.task import task
from django.conf import settings
from django.db import transaction

# Third Party
from requests.exceptions import HTTPError

# DocumentCloud
from documentcloud.common.environment import httpsub, storage
from documentcloud.documents.choices import Status
from documentcloud.documents.models import Document

if settings.ENVIRONMENT.startswith("local"):
    # pylint: disable=unused-import
    from documentcloud.documents.local_tasks import (
        process_file_internal,
        extract_images,
        ocr_pages,
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
            json={"doc_id": document_pk, "slug": document.slug, "type": "process_pdf"},
        )


@task
def process(document_pk, slug):
    """Start the processing"""
    httpsub.post(
        settings.DOC_PROCESSING_URL, json={"doc_id": document_pk, "slug": slug}
    )


@task
def create_redaction(document_pk, slug, redactions):
    """Start the processing"""
    httpsub.post(
        settings.DOC_PROCESSING_URL,
        json={
            "method": "redact",
            "doc_id": document_pk,
            "slug": slug,
            "redactions": redactions,
        },
    )


@task
def delete_document(path):
    storage.delete(path)


@task
def update_access(document_pk):
    document = Document.objects.get(pk=document_pk)
    access = "public" if document.public else "private"
    storage.set_access(document.doc_path, access)
    storage.set_access(document.pages_path, access)
