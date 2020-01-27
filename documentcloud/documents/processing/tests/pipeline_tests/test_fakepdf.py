# Django
from django.test import TestCase

from .fake_pdf import FakePdf


class FakePdfTest(TestCase):
    def test_page_count(self):
        pdf = FakePdf("...")
        self.assertEqual(pdf.page_count, 3)

        pdf = FakePdf("")
        self.assertEqual(pdf.page_count, 0)

        pdf = FakePdf("..o.o")
        self.assertEqual(pdf.page_count, 5)

    def test_needs_ocr(self):
        pdf = FakePdf("...")
        self.assertFalse(pdf.needs_ocr(0))
        self.assertFalse(pdf.needs_ocr(1))
        self.assertFalse(pdf.needs_ocr(2))

        pdf = FakePdf("..o.o")
        self.assertFalse(pdf.needs_ocr(0))
        self.assertFalse(pdf.needs_ocr(1))
        self.assertTrue(pdf.needs_ocr(2))
        self.assertFalse(pdf.needs_ocr(3))
        self.assertTrue(pdf.needs_ocr(4))
