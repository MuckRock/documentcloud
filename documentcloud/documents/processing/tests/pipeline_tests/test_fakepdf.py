# Local
from .fake_pdf import FakePdf


class FakePdfTest:
    def test_page_count(self):
        pdf = FakePdf("...")
        assert pdf.page_count == 3

        pdf = FakePdf("")
        assert pdf.page_count == 0

        pdf = FakePdf("..o.o")
        assert pdf.page_count == 5

    def test_needs_ocr(self):
        pdf = FakePdf("...")
        assert not pdf.needs_ocr(0)
        assert not pdf.needs_ocr(1)
        assert not pdf.needs_ocr(2)

        pdf = FakePdf("..o.o")
        assert not pdf.needs_ocr(0)
        assert not pdf.needs_ocr(1)
        assert pdf.needs_ocr(2)
        assert not pdf.needs_ocr(3)
        assert pdf.needs_ocr(4)
