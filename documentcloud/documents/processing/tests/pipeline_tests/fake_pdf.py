class FakePdf:
    def __init__(self, pages):
        """Initializes the fake PDF with a string containing its pages.
        
        The pages are specified in a format indicating which pages need "OCR".
        For example:
        
          `..o.o`

        indicates a 5 page PDF document where the 3rd and 5th pages need OCR.
        
        """
        self.pages = pages
        self.page_count = len(pages)

    def needs_ocr(self, page_number):
        """Returns whether the 0-based page number requires OCR or not."""
        return self.pages[page_number] == "o"

    def redact(self, pages):
        """Redact pages by making them need OCR."""
        for page in pages:
            self.pages = self.pages[:page] + "o" + self.pages[page + 1 :]


class FakePage:
    def __init__(self, has_text):
        self.has_text = has_text

    @property
    def text(self):
        if self.has_text:
            return "text"
        return ""
