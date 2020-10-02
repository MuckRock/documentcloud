# Django
from celery.task import task

# DocumentCloud
from documentcloud.documents.processing.document_conversion.main import (
    run_document_conversion,
)
from documentcloud.documents.processing.info_and_image.main import (
    assemble_page_text,
    extract_image,
    finish_import,
    import_document,
    process_page_cache,
    process_pdf,
    redact_doc,
    start_import,
)
from documentcloud.documents.processing.ocr.main import run_tesseract
from documentcloud.documents.processing.document_conversion.main import (
    run_document_conversion,
)

# Set a high soft time limit so document processing can
# proceed without timing out.
SOFT_TIME_LIMIT = 10000


@task(soft_time_limit=SOFT_TIME_LIMIT)
def process_file_internal(options):
    process_pdf(options)


@task(soft_time_limit=SOFT_TIME_LIMIT)
def document_convert(options):
    run_document_conversion(options)


@task(soft_time_limit=SOFT_TIME_LIMIT)
def cache_pages(options):
    process_page_cache(options)


@task(soft_time_limit=SOFT_TIME_LIMIT)
def extract_images(data):
    extract_image(data)


@task(soft_time_limit=SOFT_TIME_LIMIT)
def ocr_pages(data):
    run_tesseract(data, None)


@task(soft_time_limit=SOFT_TIME_LIMIT)
def assemble_text(data):
    assemble_page_text(data, None)


@task(soft_time_limit=SOFT_TIME_LIMIT)
def redact_document(data):
    redact_doc(data, None)


@task(soft_time_limit=SOFT_TIME_LIMIT)
def start_import_process(data):
    start_import(data, None)


@task(soft_time_limit=SOFT_TIME_LIMIT)
def import_doc(data):
    import_document(data, None)


@task(soft_time_limit=SOFT_TIME_LIMIT)
def finish_import_process(data):
    finish_import(data, None)
