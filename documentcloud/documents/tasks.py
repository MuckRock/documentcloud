# Django
from celery.task import task
from django.conf import settings
from django.db import transaction

# Third Party
from requests.exceptions import HTTPError

# DocumentCloud
from documentcloud.documents.choices import Status
from documentcloud.documents.models import Document
from documentcloud.environment.environment import httpsub, storage

if settings.ENVIRONMENT == "local":
    # pylint: disable=unused-import
    from documentcloud.documents.local_tasks import (
        process_file,
        process_file_internal,
        extract_images,
        ocr_pages,
    )


@task(autoretry_for=(HTTPError,), retry_backoff=30)
def fetch_file_url(file_url, document_pk):
    """Download a file to S3 when given a URL on document creation"""
    document = Document.objects.get(pk=document_pk)
    path = f"documents/{document_pk}/{document.slug}.pdf"
    try:
        storage.fetch_url(file_url, f"{settings.DOCUMENT_BUCKET}/{path}")
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
            settings.DOC_PROCESSING_URL, json={"document": document_pk, "path": path}
        )


@task
def process(document_pk, path):
    """Start the processing"""
    httpsub.post(
        settings.DOC_PROCESSING_URL, json={"document": document_pk, "path": path}
    )
