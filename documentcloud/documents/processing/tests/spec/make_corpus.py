#!/usr/bin/env python3
"""
Build the input documents for the processing pipeline test spec.

Each test case directory under `documents/` gets an `input/` PDF built
deterministically with PyMuPDF.  This script only needs to be re-run when the
corpus itself changes — the inputs are committed to the repository so that the
golden outputs always correspond to a known set of input bytes.

Usage:
    python make_corpus.py [case ...]     # default: all cases
"""

# Standard Library
import sys
from pathlib import Path

# Third Party
import pymupdf

SPEC_DIR = Path(__file__).parent
DOCUMENTS_DIR = SPEC_DIR / "documents"

LETTER = (612, 792)  # US Letter in PDF points
A5_LANDSCAPE = (595, 420)

# Text sized and spaced generously so the scanned pages OCR cleanly
SCAN_FONT_SIZE = 28
TEXT_FONT_SIZE = 13


def add_text_page(pdf, lines, size=LETTER, font_size=TEXT_FONT_SIZE):
    """Add a page with an embedded text layer."""
    page = pdf.new_page(width=size[0], height=size[1])
    y = 90
    for line in lines:
        page.insert_text((72, y), line, fontname="helv", fontsize=font_size)
        y += font_size * 1.8
    return page


def add_scanned_page(pdf, lines, size=LETTER, dpi=150):
    """Add an image-only page: the text is rasterized so there is no text
    layer, forcing the page through OCR."""
    # Render the text onto a scratch page, then insert it as an image
    scratch = pymupdf.open()
    page = scratch.new_page(width=size[0], height=size[1])
    y = 120
    for line in lines:
        page.insert_text((72, y), line, fontname="helv", fontsize=SCAN_FONT_SIZE)
        y += SCAN_FONT_SIZE * 2
    png_bytes = page.get_pixmap(dpi=dpi).tobytes("png")
    scratch.close()

    image_page = pdf.new_page(width=size[0], height=size[1])
    image_page.insert_image(image_page.rect, stream=png_bytes)
    return image_page


def build_text_1page(pdf):
    add_text_page(
        pdf,
        [
            "PROCESSING PIPELINE TEST SPEC",
            "Case: single page with an embedded text layer.",
            "This page must not be OCR'd; its text is extracted directly",
            "from the PDF and the output PDF keeps the original text layer.",
        ],
    )


def build_text_3page(pdf):
    for number, word in enumerate(["one", "two", "three"], start=1):
        add_text_page(
            pdf,
            [
                f"Page {word} of the multi-page text document.",
                f"The page text files must contain this page {number} marker.",
            ],
        )


def build_scan_2page(pdf):
    add_scanned_page(pdf, ["SCANNED PAGE ONE", "NO TEXT LAYER HERE"])
    add_scanned_page(pdf, ["SCANNED PAGE TWO", "EVERY PAGE IS OCRD"])


def build_mixed_2page(pdf):
    add_text_page(
        pdf,
        [
            "Mixed document, page one has an embedded text layer.",
            "Only the second page goes through OCR.",
        ],
    )
    add_scanned_page(pdf, ["MIXED PAGE TWO", "THIS PAGE IS SCANNED"])


def build_force_ocr_1page(pdf):
    add_text_page(
        pdf,
        [
            "FORCE OCR TEST DOCUMENT",
            "This page has an embedded text layer, but the case settings",
            "use force_ocr, so the pipeline must OCR it anyway.",
        ],
        font_size=SCAN_FONT_SIZE // 2,
    )


def build_mixed_sizes_2page(pdf):
    add_text_page(pdf, ["Letter sized page.", "612 by 792 points."], size=LETTER)
    add_text_page(
        pdf,
        ["A5 landscape page.", "595 by 420 points."],
        size=A5_LANDSCAPE,
    )


def build_blank_1page(pdf):
    pdf.new_page(width=LETTER[0], height=LETTER[1])


def build_redact_2page(pdf):
    add_text_page(
        pdf,
        [
            "Redaction test document, page one is untouched.",
            "Only page two receives a redaction.",
        ],
    )
    add_text_page(
        pdf,
        [
            "Page two before redaction.",
            "SECRET LINE THAT GETS REDACTED",
            "Visible line under the redaction.",
        ],
    )


BUILDERS = {
    "text-1page": build_text_1page,
    "text-3page": build_text_3page,
    "scan-2page": build_scan_2page,
    "mixed-2page": build_mixed_2page,
    "force-ocr-1page": build_force_ocr_1page,
    "mixed-sizes-2page": build_mixed_sizes_2page,
    "blank-1page": build_blank_1page,
    "redact-2page": build_redact_2page,
}


def main(argv):
    names = argv or sorted(BUILDERS)
    for name in names:
        builder = BUILDERS[name]
        input_dir = DOCUMENTS_DIR / name / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        pdf = pymupdf.open()
        builder(pdf)
        output = input_dir / f"{name}.pdf"
        pdf.save(str(output), garbage=4, deflate=True, deflate_images=True)
        pdf.close()
        print(f"wrote {output}")


if __name__ == "__main__":
    main(sys.argv[1:])
