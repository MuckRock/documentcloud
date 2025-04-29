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
        responsive = query.params.get("responsive", "1") == "1"
        width, height = self.get_dimensions(document, max_width, max_height)
        style = self.get_style(responsive, max_width, max_height)
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
        if query:
            src = f"{src}?{query}"
        return {"src": src, **extra}

    def get_dimensions(self, document, max_width, max_height):
        default_width = 800
        aspect_ratio = document.aspect_ratio
        if max_width and max_height:
            # preserve user intention and break aspect ratio
            return max_width, max_height
        elif max_width:
            return max_width, int(max_width / aspect_ratio)
        elif max_height:
            return int(max_height * aspect_ratio), max_height
        else:
            return default_width, int(default_width / aspect_ratio)

    def get_style(self, responsive, max_width, max_height):
        # Responsive is now the default width setting
        # 100% width and 100vh - 100px height (800px fallback for old browsers)
        style = " width: 100%; height: 800px; height: calc(100vh - 100px);"

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
        src = settings.DOCCLOUD_EMBED_URL + document.get_absolute_url()
        if query:
            src = f"{src}?{query}"
        if page:
            src = f"{src}#document/p{page}"
        return {
            "src": src,
            **extra,
        }


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
    width = 750

    def response(self, request, query, max_width=None, max_height=None, **kwargs):
        document = get_object_or_404(
            Document.objects.get_viewable(request.user), pk=kwargs["doc_pk"]
        )
        note = get_object_or_404(
            document.notes.get_viewable(request.user, document), pk=kwargs["pk"]
        )

        height = None
        if max_width and max_width < self.width:
            width = max_width
        else:
            width = self.width
        oembed = {"title": note.title, "width": width, "height": height}
        # pylint: disable=consider-using-f-string
        context = {
            "pk": note.pk,
            "loader_src": f"{settings.DOCCLOUD_URL}/notes/loader.js",
            "note_src": "{}{}annotations/{}.js".format(
                settings.DOCCLOUD_EMBED_URL, document.get_absolute_url(), note.pk
            ),
            "note_html_src": "{}{}annotations/{}".format(
                settings.DOCCLOUD_EMBED_URL, document.get_absolute_url(), note.pk
            ),
            **oembed,
        }
        template = get_template(self.template)
        oembed["html"] = template.render(context)
        return self.oembed(**oembed)
