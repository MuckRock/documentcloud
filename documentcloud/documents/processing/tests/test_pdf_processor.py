# Standard Library
import os
import tempfile

# DocumentCloud
from documentcloud.common.environment.local.storage import storage
from documentcloud.documents.processing.info_and_image.pdfium import (
    StorageHandler,
    Workspace,
)
from documentcloud.documents.processing.tests.imagediff import same_images
from documentcloud.documents.processing.tests.report_test_case import ReportTestCase
from documentcloud.documents.processing.tests.textdiff import same_text

base_dir = os.path.dirname(os.path.abspath(__file__))
pdfs = os.path.join(base_dir, "pdfs")
images = os.path.join(base_dir, "images")
texts = os.path.join(base_dir, "texts")

with open(os.path.join(texts, "pg2.txt"), "r") as pg2_file:
    page2_text = pg2_file.read()

desired_texts = [None, page2_text, None]


class PDFProcessorTest(ReportTestCase):
    def test_read_images_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            # Start the report and embed the reference PDF.
            self.report_generator.add_subheading("Initialize document")
            pdf_path = os.path.join(pdfs, "doc_3.pdf")
            self.report_generator.add_pdf(pdf_path)

            with Workspace() as workspace, StorageHandler(
                storage, pdf_path
            ) as file_, workspace.load_document_custom(file_) as doc:
                # Assert correct page count.
                self.assertEqual(doc.page_count, 3)
                for i in range(doc.page_count):
                    page = doc.load_page(i)
                    # Render each page.
                    new_fn = "doc_3_pg{}.png".format(i)
                    new_path = os.path.join(directory, new_fn)
                    bmp = page.get_bitmap(1000, None)
                    bmp.render(storage, new_path, "png")
                    expected_image = os.path.join(pdfs, new_fn)
                    # Assert correct extracted images.
                    self.assertTrue(
                        same_images(new_path, expected_image, self.report_generator)
                    )
                    # Assert correct extracted texts.
                    text = page.text
                    expected_text = desired_texts[i]
                    if expected_text is None:
                        self.assertEqual(len(text.strip()), 0)
                        continue
                    self.assertTrue(
                        same_text(text, expected_text, self.report_generator)
                    )
