# Django
from celery.task import task

# DocumentCloud
from documentcloud.documents.processing.info_and_image.main import (
    extract_image,
    process_pdf,
)
from documentcloud.documents.processing.ocr.main import run_tesseract


@task
def process_file(options):
    process_pdf(options)


@task
def extract_images(data):
    extract_image(data)


@task
def ocr_pages(data):
    run_tesseract(data, None)
