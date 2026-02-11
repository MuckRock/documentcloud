"""
Helper functions shared by both application and processing code
"""

# Standard Library
import math

# Third Party
import pymupdf


def graft_page(positions, pdf_page):
    """Graft words with position information onto a PDF page"""

    default_fontsize = 15

    for position in positions:
        word_text = position["text"]
        text_length = pymupdf.get_text_length(
            word_text,
            fontsize=default_fontsize,
        )
        width = (position["x2"] - position["x1"]) * pdf_page.rect.width
        fontsize_optimal = int(math.floor((width / text_length) * default_fontsize))
        pdf_page.insert_text(
            point=pymupdf.Point(
                position["x1"] * pdf_page.rect.width,
                position["y2"] * pdf_page.rect.height,
            ),
            text=word_text,
            fontsize=fontsize_optimal,
            fill_opacity=0,
        )
