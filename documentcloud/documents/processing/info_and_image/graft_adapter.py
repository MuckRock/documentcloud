"""
Abstracts a context object that can be passed to graft.py
by James R. Barlow (copied unchanged from
https://github.com/jbarlow83/OCRmyPDF/blob/master/src/ocrmypdf/_graft.py).

The abstraction allows for in-memory PDF files passed in as
BytesIO objects instead of files on the filesystem.
"""


class MockPath:
    """Mocks a filesystem-like object with a non-zero file size."""

    class MockSize:
        st_size = 1  # has to be non-zero

    def __init__(self, _):
        pass

    def stat(self):
        return MockPath.MockSize


class PdfInfo:
    """Grab page information on demand"""

    class PageInfo:
        def __init__(self, rotation):
            self.rotation = rotation

    def __init__(self, doc):
        self.doc = doc

    def __getitem__(self, key):
        with self.doc.load_page(key) as page:
            # Multiply rotation by 90 to get angle in degrees
            return PdfInfo.PageInfo((page.rotation % 4) * 90)


class GraftContext:
    """Mocks a graft context object with an in-memory PDF for use with graft.py"""

    class GraftOptions:
        """Options for grafting."""

        redo_ocr = False
        keep_temporary_files = False

    def __init__(self, graft_module, pdf_document_mem_file, pdf_document):
        self.origin = pdf_document_mem_file
        self.doc = pdf_document
        self.pdfinfo = PdfInfo(self.doc)

        # Mock the graft module's pathlib Path class to return a fixed size
        graft_module.Path = MockPath

        # Hook up other mocks
        self.options = GraftContext.GraftOptions
        self.get_path = lambda _: None
