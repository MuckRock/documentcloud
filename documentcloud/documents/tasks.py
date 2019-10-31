# Django
from celery.task import task
from django.conf import settings

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


@task
def fetch_file_url(file_url, document_pk):
    # XXX error check fetch worked
    # do we want to retry for 5xx status codes?
    document = Document.objects.get(pk=document_pk)
    path = f"{document_pk}/{document.slug}.pdf"
    storage.fetch_url(file_url, f"{settings.DOCUMENT_BUCKET}/{path}")

    document.status = Status.pending
    document.save()
    httpsub.post(
        settings.DOC_PROCESSING_URL, json={"document": document_pk, "path": path}
    )
