# Django
from celery.task import task

# DocumentCloud
from documentcloud.documents.processing.info_and_image.main import (
    extract_image,
    process_pdf,
    redact_doc,
)
from documentcloud.documents.processing.ocr.main import run_tesseract

# Set a high soft time limit so document processing can
# proceed without timing out.
SOFT_TIME_LIMIT = 10000


@task(soft_time_limit=SOFT_TIME_LIMIT)
def process_file_internal(options):
    process_pdf(options)


@task(soft_time_limit=SOFT_TIME_LIMIT)
def extract_images(data):
    extract_image(data)


@task(soft_time_limit=SOFT_TIME_LIMIT)
def ocr_pages(data):
    run_tesseract(data, None)


@task(soft_time_limit=SOFT_TIME_LIMIT)
def redact_document(data):
    redact_doc(data, None)
