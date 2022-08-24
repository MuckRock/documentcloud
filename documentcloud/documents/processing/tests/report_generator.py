# Standard Library
import base64
import inspect
import os
from html import escape
from io import StringIO
from typing import IO, List, Tuple

HEADING = 0
SUBHEADING = 1

# The border styling for embedded resources.
EMBED_STYLE = "border: solid 1px gray;"


class ReportGenerator:
    """A class to generate HTML reports, primarily intended for testing.

    ReportGenerator is a class that writes an HTML file iteratively with methods to add
    headings, text, images with captions, and PDF resources. Headings and subheadings
    that are added will dynamically generate entries into a table of contents that will
    be placed at the top of the document. Resource files are base64-encoded and embedded
    within the HTML file, effectively making the outputted HTML document
    dependency-free.
    """

    def __init__(self, filename):
        self.filename: str = filename
        # Ensure directories are in place for file to be written.
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        self.html_file: IO[str] = open(filename, "w")
        self.string_io: StringIO = StringIO()
        self.toc: List[Tuple[int, str]] = []
        self.anchor_id: int = 0

        # Write the header and style sheet. Declare utf8 encoding.
        self.html_file.write(
            inspect.cleandoc(
                """<!DOCTYPE html>
            <html lang="en">
            <head>
            <meta charset="utf-8"/>
            <style>
                body {
                padding: 20px;
                }
                .figure-inline figure {
                    display: inline-block;
                }
            </style>
            </head>
        """
            )
        )

    def add_heading(self, text):
        """Add a primary header to the HTML document with a table of contents entry.

        Arguments:
            text {str} -- The title of the header.
        """
        self.string_io.write(f'<h1 id="{self.anchor_id}">{escape(text)}</h1>')
        self.toc.append((HEADING, text))
        self.anchor_id += 1

    def add_subheading(self, text):
        """Adds a secondary header to the HTML document with a table of contents entry.

        Arguments:
            text {str} -- The title of the subheader.
        """
        self.string_io.write(f'<h2 id="{self.anchor_id}">{escape(text)}</h2>')
        self.toc.append((SUBHEADING, text))
        self.anchor_id += 1

    def add_text(self, text, style=None):
        """Adds text to the HTML document in a paragraph with optional styling.

        Arguments:
            text {str} -- The text to add.

        Keyword Arguments:
            style {Optional[str]} -- If specified, a ';'-separated list of CSS
                attributes that describe the style to apply to the paragraph. For
                example, "color: red; font-style: italic;". (default: {None})
        """
        style_str = ""
        if style is not None:
            style_str = f' style="{style}"'
        self.string_io.write(f"<p{style_str}>{escape(text)}</p>")

    def add_bold(self, text):
        """Adds bold text to the HTML document.

        Arguments:
            text {str} -- The bold text to add.
        """
        return self.add_text(text, "font-weight: bold;")

    def add_image(self, png_path, caption=None):
        """Embeds an image and optional caption into the HTML document.

        Arguments:
            png_path {str} -- The full path to the PNG image to embed.

        Keyword Arguments:
            caption {Optional[str]} -- If specified, a caption that will be placed below
                the image. (default: {None})
        """
        self.string_io.write("<figure>")
        with open(png_path, "rb") as png_file:
            encoded = base64.b64encode(png_file.read()).decode("ascii")
        self.string_io.write(
            f'<img style="width: 400px; {EMBED_STYLE}"'
            f'src="data:image/png;base64,{encoded}">'
        )
        if caption is not None:
            self.string_io.write(f"<figcaption>{escape(caption)}</figcaption>")
        self.string_io.write("</figure>")

    def add_images(self, png_paths, captions=None):
        """Embeds multiple images side-by-side, each with an optional caption.

        Arguments:
            png_paths {List[str]} -- A list of fully specified paths to the PNG files
                to be embedded. The first image will be the left-most and subsequent
                ones will be stacked to the right.

        Keyword Arguments:
            captions {Optional[List[Optional[str]]]} -- If specified, a list of captions
                for each corresponding image. This list is expected to be the same
                length as the list of PNG paths. Each element can either be a caption
                or None to leave a specific image captionless. (default: {None})
        """
        self.string_io.write('<div class="figure-inline">')
        if captions is None:
            for png_path in png_paths:
                self.add_image(png_path)
        else:
            for png_path, caption in zip(png_paths, captions):
                self.add_image(png_path, caption)
        self.string_io.write("</div>")

    def add_pdf(self, pdf_path):
        """Embdes a PDF file into the HTML document.

        Arguments:
            pdf_path {str} -- The full path to the PDF resource to embed.
        """
        with open(pdf_path, "rb") as pdf_file:
            encoded = base64.b64encode(pdf_file.read()).decode("ascii")
        self.string_io.write(
            f'<embed style="{EMBED_STYLE}" width="400" height="600"'
            f'src="data:application/pdf;base64,{encoded}">'
        )

    def add_horizontal_rule(self):
        """Adds a horizontal rule into the HTML document."""
        self.string_io.write("<hr>")

    def close(self):
        """Insert the table of contents and close the HTML document for writing."""
        # Write the table of contents.
        if self.toc:
            # Write as a bulleted list.
            self.html_file.write("<ul>")
            for i, [heading, text] in enumerate(self.toc):
                if heading == HEADING:
                    self.html_file.write(f'<li><a href="#{i}">{escape(text)}</a></li>')
                elif heading == SUBHEADING:
                    # Subheadings are sub-bullets.
                    self.html_file.write(
                        f'<ul><li><a href="#{i}">{escape(text)}</a></li></ul>'
                    )
            self.html_file.write("</ul>")

        self.html_file.write(self.string_io.getvalue())
        self.string_io.close()
        self.html_file.close()
