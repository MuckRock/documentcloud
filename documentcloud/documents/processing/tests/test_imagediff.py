# Standard Library
import os

# Local
from .imagediff import same_images
from .report_test_case import ReportTestCase

base_dir = os.path.dirname(os.path.abspath(__file__))
images = os.path.join(base_dir, "images")
pdfs = os.path.join(base_dir, "pdfs")


class ImagediffTest(ReportTestCase):
    def test_same_images(self) -> None:
        # 3 different renderers, should be "identical" in imagediff.
        self.report_generator.add_subheading("Same page, different renderers")
        self.assertTrue(
            same_images(
                os.path.join(images, "imagediff_pdfium_page.png"),
                os.path.join(images, "imagediff_preview_page.png"),
                self.report_generator,
            )
        )
        self.assertTrue(
            same_images(
                os.path.join(images, "imagediff_preview_page.png"),
                os.path.join(images, "imagediff_illustrator_page.png"),
                self.report_generator,
            )
        )
        self.assertTrue(
            same_images(
                os.path.join(images, "imagediff_illustrator_page.png"),
                os.path.join(images, "imagediff_pdfium_page.png"),
                self.report_generator,
            )
        )

    def test_alterations(self) -> None:
        self.report_generator.add_subheading("Same page, minor alterations")
        self.assertFalse(
            same_images(
                os.path.join(images, "imagediff_pdfium_page.png"),
                os.path.join(images, "imagediff_alteration_orange_square.png"),
                self.report_generator,
            )
        )
        self.assertFalse(
            same_images(
                os.path.join(images, "imagediff_pdfium_page.png"),
                os.path.join(images, "imagediff_alteration_small_redaction.png"),
                self.report_generator,
            )
        )
        self.assertFalse(
            same_images(
                os.path.join(images, "imagediff_pdfium_page.png"),
                os.path.join(images, "imagediff_alteration_red_scratch.png"),
                self.report_generator,
            )
        )

    def test_different_pages(self) -> None:
        self.report_generator.add_subheading("Different pages")
        self.assertFalse(
            same_images(
                os.path.join(pdfs, "doc_3_pg0.png"),
                os.path.join(pdfs, "doc_3_pg1.png"),
                self.report_generator,
            )
        )
        self.assertFalse(
            same_images(
                os.path.join(pdfs, "doc_3_pg1.png"),
                os.path.join(pdfs, "doc_3_pg2.png"),
                self.report_generator,
            )
        )
        self.assertFalse(
            same_images(
                os.path.join(pdfs, "doc_3_pg2.png"),
                os.path.join(pdfs, "doc_3_pg0.png"),
                self.report_generator,
            )
        )
