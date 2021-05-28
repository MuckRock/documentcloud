"""
Exports a method `patch_pipeline` which mocks all aspects of the processing
pipeline necessary to unit test the full processing stack.
"""

# Standard Library
import functools
from contextlib import ExitStack
from unittest.mock import patch

# Third Party
from config import celery_app

# DocumentCloud
from documentcloud.common import path
from documentcloud.common.serverless.utils import get_redis, initialize
from documentcloud.documents.processing.tests.pipeline_tests.fake_pdf import FakePage

docs = {}

SLUG = "doc"  # Use same slug for simplicity
ID = -1  # Use negative ID to prevent overlap

INFO_AND_IMAGE = "documentcloud.documents.processing.info_and_image"
OCR = "documentcloud.documents.processing.ocr"


def init_doc(pdf):
    # Clear Redis fields
    initialize(get_redis(), ID)
    # Set the doc in faked storage
    docs[path.doc_path(ID, SLUG)] = pdf


def patch_env(env):
    # Patch environment
    dict_patched = patch.dict("os.environ", {k: f"{env[k]}" for k in env})
    patches = [dict_patched]
    for key in env:
        value = env[key]
        patches.append(patch(f"{INFO_AND_IMAGE}.main.{key}", value, create=True))
        patches.append(patch(f"{OCR}.main.{key}", value, create=True))

    stack = ExitStack()
    for patch_ in patches:
        stack.enter_context(patch_)
    return stack


# Mock methods
# pylint: disable=unused-argument
def page_loaded(page):
    pass


def cache_hit(page):
    pass


def cache_miss(page):
    pass


def cache_written(filename, cache):
    pass


def cache_read(filename, cache):
    pass


def pagespec_written():
    pass


def text_file_written(text_path, text):
    pass


def page_extracted(page_number):
    pass


def page_ocrd(page_path, upload_text_path, access, language):
    pass


def pdf_grafted(doc_id, slug, access):
    pass


def page_text_partially_patched(doc_id, slug, results):
    pass


def page_text_position_extracted(pdf, doc_id, slug, page_number, access):
    pass


def update_sent(doc_id, json):
    pass


def complete_sent(doc_id):
    pass


def error_sent(doc_id, message, fatal=False):
    pass


# Replaced methods


class Workspace:
    def __init__(self, handler, password=None):
        self.handler = handler
        self.password = password
        self.filename = handler.filename
        self.doc = docs[self.filename]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    @property
    def page_count(self):
        """Return the page count as reported by FakePdf"""
        return self.doc.page_count

    def trigger_cache(self, number):
        """Simulate loading a page and needing to access all previous pages."""
        for page in range(number + 1):
            if page in self.handler.cache:
                cache_hit(page)
            else:
                cache_miss(page)
                if self.handler.record:
                    self.handler.cache[page] = True

    def load_page(self, number):
        page_loaded(number)
        # Trigger the cache
        self.trigger_cache(number)
        return FakePage(not self.doc.needs_ocr(number))


def storage_simple_upload(_path, contents, access):
    pass


def storage_size(filename):
    return 1  # Every document is 1 byte for testing


class StorageOpen:
    """Storage open mock. We should never need a write method due to mocks"""

    def __init__(self, filename, mode):
        self.filename = filename
        self.mode = mode

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, size=None):
        return b""

    def close(self):
        pass


class PdfPlumberOpen:
    """pdfplumber open mock, simulating successfully opening a pdf"""

    def __init__(self, filename):
        self.filename = filename

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def close(self):
        pass


# Simulate cache files to accurately measure cache misses/hits
files_cached = {}


def write_cache(filename, cache):
    files_cached[filename] = cache
    cache_written(filename, cache)


def read_cache(filename):
    if filename in files_cached:
        cache_read(filename, files_cached[filename])
        return files_cached[filename]
    else:
        raise KeyError("Cache file not found")


def extract_single_page(doc_id, slug, access, page, page_number, large_image_path):
    page_extracted(page_number)
    return (100, 200)  # Arbitrary width / height


def update_pagespec(doc_id):
    pagespec_written()


def ocr_page(page_path, upload_text_path, access, language):
    page_ocrd(page_path, upload_text_path, access, language)
    return ("", b"")  # empty text and pdf contents


def graft_ocr_in_pdf(doc_id, slug, access):
    pdf_grafted(doc_id, slug, access)


def patch_partial_page_text(doc_id, slug, results):
    page_text_partially_patched(doc_id, slug, results)
    return {"pages": []}  # empty concatenated text


def write_concatenated_text_file(doc_id, slug, access, page_jsons):
    pass


def extract_text_position_for_page(pdf, doc_id, slug, page_number, access):
    page_text_position_extracted(pdf, doc_id, slug, page_number, access)


def write_text_file(text_path, text, access):
    text_file_written(text_path, text)


def redact_doc(doc_id, slug, access, redactions):
    """Redact document by ensuring redacted pages need OCR"""
    pages = [r["page_number"] for r in redactions]
    docs[path.doc_path(doc_id, slug)].redact(pages)


def send_update(_, doc_id, json):
    update_sent(doc_id, json)


def send_complete(_, doc_id):
    complete_sent(doc_id)


def send_error(_, doc_id, exc=None, message=None):
    error_sent(doc_id, exc, message)


def patch_pipeline(func):
    """Jumbo patch method to mock entire processing pipeline."""
    # pylint: disable=too-many-locals, invalid-name

    ENVIRONMENT = "documentcloud.common.environment"
    SERVERLESS = "documentcloud.common.serverless"

    WORKSPACE_LOAD_MOCK = f"{INFO_AND_IMAGE}.pdfium.Workspace.load_document_custom"
    STORAGE_OPEN_MOCK = f"{ENVIRONMENT}.storage.open"
    STORAGE_SIMPLE_UPLOAD_MOCK = f"{ENVIRONMENT}.storage.simple_upload"
    STORAGE_SIZE_MOCK = f"{ENVIRONMENT}.storage.size"
    PDF_PLUMBER_OPEN_MOCK = "pdfplumber.open"
    WRITE_CACHE_MOCK = f"{INFO_AND_IMAGE}.main.write_cache"
    READ_CACHE_MOCK = f"{INFO_AND_IMAGE}.main.read_cache"
    EXTRACT_SINGLE_PAGE_MOCK = f"{INFO_AND_IMAGE}.main.extract_single_page"
    UPDATE_PAGESPEC_MOCK = f"{INFO_AND_IMAGE}.main.update_pagespec"
    OCR_PAGE_MOCK = f"{OCR}.main.ocr_page"
    GRAFT_OCR_MOCK = f"{INFO_AND_IMAGE}.main.graft_ocr_in_pdf"
    PARTIAL_PAGE_TEXT_PATCH_MOCK = f"{INFO_AND_IMAGE}.main.patch_partial_page_text"
    WRITE_CONCATENATED_TEXT_FILE_MOCK = (
        f"{INFO_AND_IMAGE}.main.write_concatenated_text_file"
    )
    EXTRACT_TEXT_POSITION_MOCK = f"{INFO_AND_IMAGE}.main.extract_text_position_for_page"
    WRITE_TEXT_FILE_II_MOCK = f"{INFO_AND_IMAGE}.main.write_text_file"
    WRITE_TEXT_FILE_OCR_MOCK = f"{OCR}.main.write_text_file"
    REDACT_DOC_MOCK = f"{INFO_AND_IMAGE}.main.redact_document_and_overwrite"
    SEND_UPDATE_MOCK = f"{SERVERLESS}.utils.send_update"
    SEND_COMPLETE_MOCK = f"{SERVERLESS}.utils.send_complete"
    SEND_ERROR_MOCK = f"{SERVERLESS}.utils.send_error"

    MOCKS = "documentcloud.documents.processing.tests.pipeline_tests.mocks"

    # Mocked methods
    @patch(f"{MOCKS}.page_text_position_extracted")
    @patch(f"{MOCKS}.page_text_partially_patched")
    @patch(f"{MOCKS}.pdf_grafted")
    @patch(f"{MOCKS}.page_ocrd")
    @patch(f"{MOCKS}.page_extracted")
    @patch(f"{MOCKS}.text_file_written")
    @patch(f"{MOCKS}.pagespec_written")
    @patch(f"{MOCKS}.cache_read")
    @patch(f"{MOCKS}.cache_written")
    @patch(f"{MOCKS}.cache_miss")
    @patch(f"{MOCKS}.cache_hit")
    @patch(f"{MOCKS}.page_loaded")
    @patch(f"{MOCKS}.update_sent")
    @patch(f"{MOCKS}.complete_sent")
    @patch(f"{MOCKS}.error_sent")
    # Replaced methods
    @patch(WORKSPACE_LOAD_MOCK, Workspace)
    @patch(STORAGE_OPEN_MOCK, StorageOpen)
    @patch(PDF_PLUMBER_OPEN_MOCK, PdfPlumberOpen)
    @patch(STORAGE_SIMPLE_UPLOAD_MOCK, storage_simple_upload)
    @patch(STORAGE_SIZE_MOCK, storage_size)
    @patch(WRITE_CACHE_MOCK, write_cache)
    @patch(READ_CACHE_MOCK, read_cache)
    @patch(EXTRACT_SINGLE_PAGE_MOCK, extract_single_page)
    @patch(UPDATE_PAGESPEC_MOCK, update_pagespec)
    @patch(OCR_PAGE_MOCK, ocr_page)
    @patch(GRAFT_OCR_MOCK, graft_ocr_in_pdf)
    @patch(PARTIAL_PAGE_TEXT_PATCH_MOCK, patch_partial_page_text)
    @patch(WRITE_CONCATENATED_TEXT_FILE_MOCK, write_concatenated_text_file)
    @patch(EXTRACT_TEXT_POSITION_MOCK, extract_text_position_for_page)
    @patch(WRITE_TEXT_FILE_II_MOCK, write_text_file)
    @patch(WRITE_TEXT_FILE_OCR_MOCK, write_text_file)
    @patch(REDACT_DOC_MOCK, redact_doc)
    @patch(SEND_UPDATE_MOCK, send_update)
    @patch(SEND_COMPLETE_MOCK, send_complete)
    @patch(SEND_ERROR_MOCK, send_error)
    @patch(f"{SERVERLESS}.error_handling.USE_TIMEOUT", False)
    @functools.wraps(func)
    def functor(
        test,
        mock_error_sent,
        mock_complete_sent,
        mock_update_sent,
        mock_page_loaded,
        mock_cache_hit,
        mock_cache_miss,
        mock_cache_written,
        mock_cache_read,
        mock_pagespec_written,
        mock_text_file_written,
        mock_page_extracted,
        mock_page_ocrd,
        mock_pdf_grafted,
        mock_page_text_partially_patched,
        mock_page_text_position_extracted,
    ):
        # pylint: disable=too-many-arguments
        # Patch Celery config
        initial_eager = celery_app.conf.task_always_eager
        celery_app.conf.task_always_eager = True

        # Pass lower-level mocks in a dict structure for caller
        result = func(
            test,
            {
                "page_loaded": mock_page_loaded,
                "cache_hit": mock_cache_hit,
                "cache_miss": mock_cache_miss,
                "cache_written": mock_cache_written,
                "cache_read": mock_cache_read,
                "pagespec_written": mock_pagespec_written,
                "text_file_written": mock_text_file_written,
                "page_extracted": mock_page_extracted,
                "page_ocrd": mock_page_ocrd,
                "pdf_grafted": mock_pdf_grafted,
                "page_text_partially_patched": mock_page_text_partially_patched,
                "page_text_position_extracted": mock_page_text_position_extracted,
                "update_sent": mock_update_sent,
                "complete_sent": mock_complete_sent,
                "error_sent": mock_error_sent,
            },
        )

        # Restore Celery config
        celery_app.conf.task_always_eager = initial_eager
        return result

    return functor
