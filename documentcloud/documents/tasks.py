# Django
from celery.task import task
from django.conf import settings
from django.db import transaction

# Third Party
from requests.exceptions import HTTPError

# DocumentCloud
from documentcloud.documents.choices import Status
from documentcloud.documents.models import Document
from documentcloud.documents.processing.info_and_image.main import (
    extract_image,
    process_pdf,
)
from documentcloud.documents.processing.ocr.main import run_tesseract
from documentcloud.environment.environment import httpsub, storage


@task
def process_file(options):
    process_pdf(options)


@task
def extract_images(data):
    extract_image(data)


@task
def ocr_pages(data):
    run_tesseract(data, None)


@task(autoretry_for=(HTTPError,), retry_backoff=30)
def fetch_file_url(file_url, document_pk):
    document = Document.objects.get(pk=document_pk)
    path = f"{document_pk}/{document.slug}.pdf"
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
