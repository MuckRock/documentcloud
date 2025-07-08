# Django
from django.conf import settings
from django.template.loader import get_template
from rest_framework.generics import get_object_or_404

# Standard Library
import re

# DocumentCloud
from documentcloud.documents.models import Document
from documentcloud.oembed.oembed import RichOEmbed
from documentcloud.oembed.registry import register

DOCCLOUD_URL_REGEX = (
    r"https?://((www|beta|embed)[.]"
    + settings.OEMBED_URL_REGEX
    + r")?documentcloud[.]org"
)

RESIZE_SCRIPT = f"{settings.DOCCLOUD_EMBED_URL}/embed/resize.js"


@register
class DocumentOEmbed(RichOEmbed):
    template = "oembed/document.html"
    patterns = [
        # viewer url
        re.compile(rf"^{DOCCLOUD_URL_REGEX}/documents/(?P<pk>[0-9]+)[\w.-]*/?$"),
        # api url
        re.compile(rf"^{settings.DOCCLOUD_API_URL}/api/documents/(?P<pk>[0-9]+)/?$"),
    ]

    def response(self, request, query, max_width=None, max_height=None, **kwargs):
        document = get_object_or_404(
            Document.objects.get_viewable(request.user), pk=kwargs["pk"]
        )
        width, height = self.get_dimensions(document, max_width, max_height)
        style = self.get_style(document, max_width, max_height)
        oembed = {
            "title": document.title,
            "width": width,
            "height": height,
            "style": style,
        }
        context = self.get_context(document, query, oembed, **kwargs)
        template = get_template(self.template)
        oembed["html"] = template.render(context)
        oembed.pop("style")
        return self.oembed(**oembed)

    def get_context(self, document, query, extra, **kwargs):
        src = settings.DOCCLOUD_EMBED_URL + document.get_absolute_url()
        src = f"{src}?embed=1"
        if query:
            src = f"{src}&{query}"
        return {"src": src, **extra}

    def get_dimensions(self, document, max_width, max_height):
        width, height = document.page_size(0)
        aspect_ratio = width / height
        if max_width and max_height:
            # preserve user intention and break aspect ratio
            return max_width, max_height
        elif max_width:
            return max_width, int(max_width / aspect_ratio)
        elif max_height:
            return int(max_height * aspect_ratio), max_height
        else:
            return width, height

    def get_style(self, document, max_width=None, max_height=None):
        width, height = document.page_size(0)
        style = f"border: 1px solid #d8dee2; border-radius: 0.5rem; width: 100%; height: 100%; aspect-ratio: {width} / {height};"

        if max_width:
            style += f" max-width: {max_width}px;"
        if max_height:
            style += f" max-height: {max_height}px;"
        return style


@register
class PageOEmbed(DocumentOEmbed):
    template = "oembed/page.html"
    patterns = [
        # page hash
        re.compile(
            rf"^{DOCCLOUD_URL_REGEX}/documents/"
            r"(?P<pk>[0-9]+)[\w.-]*/?#document/p(?P<page>[0-9]+)$"
        ),
        # old url
        re.compile(
            rf"^{DOCCLOUD_URL_REGEX}/documents/"
            r"(?P<pk>[0-9]+)[\w.-]*/pages/(?P<page>[0-9]+)(.html)?/?$"
        ),
    ]

    def get_context(self, document, query, extra, **kwargs):
        page = int(kwargs["page"])
        src = f"{settings.DOCCLOUD_EMBED_URL}/documents/{document.pk}/pages/{page}/"
        src = f"{src}?embed=1"
        if query:
            src = f"{src}&{query}"
        return {
            "src": src,
            "resize_script": RESIZE_SCRIPT,
            **extra,
        }

    def get_style(self, document, max_width=None, max_height=None, page=0):
        width, height = document.page_size(page)
        style = f"border: none; width: 100%; height: 100%; aspect-ratio: {width} / {height};"

        if max_width:
            style += f" max-width: {max_width}px;"
        if max_height:
            style += f" max-height: {max_height}px;"
        return style


@register
class NoteOEmbed(RichOEmbed):
    template = "oembed/note.html"
    patterns = [
        # note hash
        re.compile(
            rf"^{DOCCLOUD_URL_REGEX}/documents/(?P<doc_pk>[0-9]+)[\w.-]*/?"
            r"#document/p(?P<page>[0-9]+)/a(?P<pk>[0-9]+)$"
        ),
        # old url
        re.compile(
            rf"^{DOCCLOUD_URL_REGEX}/documents/"
            r"(?P<doc_pk>[0-9]+)[\w.-]*/annotations/(?P<pk>[0-9]+)(.html)?/?$"
        ),
        # api url
        re.compile(
            rf"^{settings.DOCCLOUD_API_URL}/api/documents/(?P<doc_pk>[0-9]+)/"
            r"notes/(?P<pk>[0-9]+)/?$"
        ),
    ]

    def response(self, request, query, max_width=None, max_height=None, **kwargs):
        document = get_object_or_404(
            Document.objects.get_viewable(request.user), pk=kwargs["doc_pk"]
        )
        note = get_object_or_404(
            document.notes.get_viewable(request.user, document), pk=kwargs["pk"]
        )
        oembed = {"title": note.title}
        src = (
            f"{settings.DOCCLOUD_EMBED_URL}/documents/"
            f"{document.pk}/annotations/{note.pk}/"
        )
        src = f"{src}?embed=1"
        if query:
            src = f"{src}&{query}"

        width, height, note_width, note_height = self.get_dimensions(document, note)

        context = {
            "src": src,
            "title": note.title,
            "style": self.get_style(document, note, max_width, max_height),
            "width": note_width,
            "height": note_height,
            "resize_script": RESIZE_SCRIPT,
        }
        template = get_template(self.template)
        oembed["html"] = template.render(context)
        return self.oembed(**oembed)

    def get_dimensions(self, document, note):
        page = note.page_number - 1
        width, height = document.page_size(page)
        note_width = width * (note.x2 - note.x1)
        note_height = height * (note.y2 - note.y1)

        return (width, height, note_width, note_height)

    def get_style(self, document, note, max_width=None, max_height=None):

        width, height, note_width, note_height = self.get_dimensions(document, note)

        style = f"border: 1px solid #d8dee2; border-radius: 0.5rem; width: 100%; height: 100%; aspect-ratio: {note_width} / {note_height};"
        if max_width:
            style += f" max-width: {max_width}px;"
        if max_height:
            style += f" max-height: {max_height}px;"
        return style
