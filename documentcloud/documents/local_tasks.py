# Django
from celery import shared_task

# DocumentCloud
from documentcloud.documents.processing.document_conversion.main import (
    run_document_conversion,
)
from documentcloud.documents.processing.info_and_image.main import (
    assemble_page_text,
    extract_image,
    extract_text_position,
    finish_import,
    import_document,
    modify_doc,
    process_page_cache,
    process_pdf,
    redact_doc,
    start_import,
)
from documentcloud.documents.processing.ocr.main import run_tesseract
from documentcloud.documents.processing.utils.main import retry_errors

# Set a high soft time limit so document processing can
# proceed without timing out.
SOFT_TIME_LIMIT = 10000


@shared_task(soft_time_limit=SOFT_TIME_LIMIT)
def process_file_internal(options):
    process_pdf(options)


@shared_task(soft_time_limit=SOFT_TIME_LIMIT)
def document_convert(options):
    run_document_conversion(options)


@shared_task(soft_time_limit=SOFT_TIME_LIMIT)
def cache_pages(options):
    process_page_cache(options)


@shared_task(soft_time_limit=SOFT_TIME_LIMIT)
def extract_images(data):
    extract_image(data)


@shared_task(soft_time_limit=SOFT_TIME_LIMIT)
def ocr_pages(data):
    run_tesseract(data, None)


@shared_task(soft_time_limit=SOFT_TIME_LIMIT)
def assemble_text(data):
    assemble_page_text(data, None)


@shared_task(soft_time_limit=SOFT_TIME_LIMIT)
def text_position_extract(data):
    extract_text_position(data, None)


@shared_task(soft_time_limit=SOFT_TIME_LIMIT)
def redact_document(data):
    redact_doc(data, None)


@shared_task(soft_time_limit=SOFT_TIME_LIMIT)
def modify_document(data):
    modify_doc(data, None)


@shared_task(soft_time_limit=SOFT_TIME_LIMIT)
def start_import_process(data):
    start_import(data, None)


@shared_task(soft_time_limit=SOFT_TIME_LIMIT)
def import_doc(data):
    import_document(data, None)


@shared_task(soft_time_limit=SOFT_TIME_LIMIT)
def finish_import_process(data):
    finish_import(data, None)


@shared_task(soft_time_limit=SOFT_TIME_LIMIT)
def retry_errors_local(data):
    retry_errors(data, None)
