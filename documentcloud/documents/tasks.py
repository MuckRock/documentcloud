# DocumentCloud
from documentcloud.documents.models import Document
from documentcloud.documents.processing.info_and_image.main import (
    extract_image,
    process_pdf,
)
from documentcloud.documents.processing.ocr.main import run_tesseract
from documentcloud.documents.solr import solr
from documentcloud.taskapp.celery import app


@app.task
def process_file(options):
    process_pdf(options)


@app.task
def extract_images(data):
    extract_image(data)


@app.task
def ocr_pages(data):
    run_tesseract(data, None)