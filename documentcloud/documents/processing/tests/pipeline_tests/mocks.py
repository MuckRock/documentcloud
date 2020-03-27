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


def pagespec_written(pagespec):
    pass


def text_file_written(text_path, text):
    pass


def page_extracted(page_number):
    pass


def page_ocrd(page_path):
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


def extract_single_page(doc_id, slug, page, page_number, large_image_path):
    page_extracted(page_number)
    return (100, 200)  # Arbitrary width / height


def update_pagespec(doc_id, slug, crunched_pagespec):
    pagespec_written(crunched_pagespec)


def ocr_page(page_path):
    page_ocrd(page_path)


def write_text_file(text_path, text):
    text_file_written(text_path, text)


def redact_doc(doc_id, slug, redactions):
    """Redact document by ensuring redacted pages need OCR"""
    pages = [r["page_number"] for r in redactions]
    docs[path.doc_path(doc_id, slug)].redact(pages)


def send_update(_, doc_id, json):
    update_sent(doc_id, json)


def send_complete(_, doc_id):
    complete_sent(doc_id)


def send_error(_, doc_id, message, fatal=False):
    error_sent(doc_id, message, fatal)


def patch_pipeline(func):
    """Jumbo patch method to mock entire processing pipeline."""
    # pylint: disable=too-many-locals, invalid-name

    ENVIRONMENT = "documentcloud.common.environment"
    SERVERLESS = "documentcloud.common.serverless"

    WORKSPACE_LOAD_MOCK = f"{INFO_AND_IMAGE}.pdfium.Workspace.load_document_custom"
    STORAGE_OPEN_MOCK = f"{ENVIRONMENT}.storage.open"
    STORAGE_SIZE_MOCK = f"{ENVIRONMENT}.storage.size"
    WRITE_CACHE_MOCK = f"{INFO_AND_IMAGE}.main.write_cache"
    READ_CACHE_MOCK = f"{INFO_AND_IMAGE}.main.read_cache"
    EXTRACT_SINGLE_PAGE_MOCK = f"{INFO_AND_IMAGE}.main.extract_single_page"
    UPDATE_PAGESPEC_MOCK = f"{INFO_AND_IMAGE}.main.update_pagespec"
    OCR_PAGE_MOCK = f"{OCR}.main.ocr_page"
    WRITE_TEXT_FILE_II_MOCK = f"{INFO_AND_IMAGE}.main.write_text_file"
    WRITE_TEXT_FILE_OCR_MOCK = f"{OCR}.main.write_text_file"
    REDACT_DOC_MOCK = f"{INFO_AND_IMAGE}.main.redact_document_and_overwrite"
    SEND_UPDATE_MOCK = f"{SERVERLESS}.utils.send_update"
    SEND_COMPLETE_MOCK = f"{SERVERLESS}.utils.send_complete"
    SEND_ERROR_MOCK = f"{SERVERLESS}.utils.send_error"

    MOCKS = "documentcloud.documents.processing.tests.pipeline_tests.mocks"

    # Mocked methods
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
    @patch(STORAGE_SIZE_MOCK, storage_size)
    @patch(WRITE_CACHE_MOCK, write_cache)
    @patch(READ_CACHE_MOCK, read_cache)
    @patch(EXTRACT_SINGLE_PAGE_MOCK, extract_single_page)
    @patch(UPDATE_PAGESPEC_MOCK, update_pagespec)
    @patch(OCR_PAGE_MOCK, ocr_page)
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
                "update_sent": mock_update_sent,
                "complete_sent": mock_complete_sent,
                "error_sent": mock_error_sent,
            },
        )

        # Restore Celery config
        celery_app.conf.task_always_eager = initial_eager
        return result

    return functor
