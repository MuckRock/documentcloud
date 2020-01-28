# Django
from django.test import TestCase

# DocumentCloud
from documentcloud.common.environment import encode_pubsub_data, publisher
from documentcloud.documents.processing.info_and_image.main import (
    PDF_PROCESS_TOPIC,
    REDACT_TOPIC,
)
from documentcloud.documents.processing.tests.pipeline_tests.fake_pdf import FakePdf
from documentcloud.documents.processing.tests.pipeline_tests.mocks import (
    ID,
    SLUG,
    init_doc,
    patch_pipeline,
)


def trigger_processing():
    """Triggers PDF processing via pubsub."""
    publisher.publish(
        PDF_PROCESS_TOPIC, encode_pubsub_data({"doc_id": ID, "slug": SLUG})
    )


def trigger_redacting(page_numbers):
    """Triggers redaction processing via pubsub."""
    publisher.publish(
        REDACT_TOPIC,
        encode_pubsub_data(
            {
                "doc_id": ID,
                "slug": SLUG,
                "redactions": [{"page": page_number} for page_number in page_numbers],
            }
        ),
    )


def reset_mocks(mocks):
    for mock in mocks:
        mocks[mock].reset_mock()


class PipelineTest(TestCase):
    @patch_pipeline
    def test_3pg_ocr(self, mocks):
        init_doc(FakePdf("ooo"))
        trigger_processing()
        assert mocks["page_extracted"].call_count == 3
        assert mocks["page_ocrd"].call_count == 3

    @patch_pipeline
    def test_3pg_no_ocr(self, mocks):
        init_doc(FakePdf("..."))
        trigger_processing()
        assert mocks["page_extracted"].call_count == 3
        # No pages need to be OCRd when text is extractable
        assert mocks["page_ocrd"].call_count == 0

    @patch_pipeline
    def test_5pg_half_ocr(self, mocks):
        init_doc(FakePdf(".o.o."))
        trigger_processing()
        assert mocks["page_extracted"].call_count == 5
        assert mocks["page_ocrd"].call_count == 2

    @patch_pipeline
    def test_redaction(self, mocks):
        init_doc(FakePdf("..."))
        trigger_processing()

        # Redact the middle page
        reset_mocks(mocks)
        trigger_redacting([1])
        # Only 1 page should be processed, but the cache is rebuilt
        assert mocks["cache_miss"].call_count == 3
        assert mocks["page_loaded"].call_count == 2  # 1 + 1
        assert mocks["page_extracted"].call_count == 1
        assert mocks["page_ocrd"].call_count == 1

    @patch_pipeline
    def test_cache_misses(self, mocks):
        init_doc(FakePdf("..."))
        trigger_processing()

        assert mocks["cache_miss"].call_count == 3

    @patch_pipeline
    def test_cache_batching(self, mocks):
        init_doc(FakePdf("....."))
        trigger_processing()

        # Cache should be written only once
        assert mocks["cache_written"].call_count == 1

    @patch_pipeline
    def test_cache_dirty_batching(self, mocks):
        init_doc(FakePdf("....."))
        trigger_processing()

        # Redact the last two pages
        reset_mocks(mocks)
        trigger_redacting([3, 4])

        # Cache should only be written once
        assert mocks["cache_written"].call_count == 1

        # Cache should be missed number of pages times
        assert mocks["cache_miss"].call_count == 5

        # Two pages should be extracted
        assert mocks["page_extracted"].call_count == 2
        assert mocks["page_ocrd"].call_count == 2
