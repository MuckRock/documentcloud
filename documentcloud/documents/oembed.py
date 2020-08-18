# Django
from django.conf import settings
from django.template.loader import get_template
from rest_framework.generics import get_object_or_404

# Standard Library
import re
import time

# DocumentCloud
from documentcloud.common.path import page_image_path, page_text_path
from documentcloud.documents.models import Document
from documentcloud.oembed.oembed import RichOEmbed
from documentcloud.oembed.registry import register


@register
class DocumentOEmbed(RichOEmbed):
    template = "oembed/document.html"
    patterns = [
        # viewer url
        re.compile(rf"^{settings.DOCCLOUD_URL}/documents/(?P<pk>[0-9]+)[a-z0-9_-]*/?$"),
        # api url
        re.compile(rf"^{settings.DOCCLOUD_API_URL}/api/documents/(?P<pk>[0-9]+)/?$"),
    ]

    def response(self, request, query, max_width=None, max_height=None, **kwargs):
        document = get_object_or_404(
            Document.objects.get_viewable(request.user), pk=kwargs["pk"]
        )

        width, height = self.get_dimensions(document, max_width, max_height)
        oembed = {"title": document.title, "width": width, "height": height}
        context = self.get_context(document, query, oembed, **kwargs)
        template = get_template(self.template)
        oembed["html"] = template.render(context)
        return self.oembed(**oembed)

    def get_context(self, document, query, extra, **kwargs):
        # pylint: disable=unused-argument
        src = settings.DOCCLOUD_EMBED_URL + document.get_absolute_url()
        if query:
            src = f"{src}?{query}"
        return {"src": src, **extra}

    def get_dimensions(self, document, max_width, max_height):
        default_width = 700
        aspect_ratio = document.aspect_ratio
        if max_width and max_height:
            if max_width / aspect_ratio > max_height:
                # cap based on max_height
                return int(max_height * aspect_ratio), max_height
            else:
                # cap based on max width
                return max_width, int(max_width / aspect_ratio)
        elif max_width:
            return max_width, int(max_width / aspect_ratio)
        elif max_height:
            return int(max_height * aspect_ratio), max_height
        else:
            return default_width, int(default_width / aspect_ratio)


@register
class PageOEmbed(DocumentOEmbed):
    template = "oembed/page.html"
    patterns = [
        re.compile(
            rf"^{settings.DOCCLOUD_URL}/documents/"
            r"(?P<pk>[0-9]+)[a-z0-9_-]*/?#document/p(?P<page>[0-9]+)$"
        )
    ]

    def get_dimensions(self, document, max_width, max_height):
        default_width = 700
        if max_width:
            return (min(max_width, default_width), None)
        else:
            return default_width, None

    def get_context(self, document, query, extra, **kwargs):
        page = int(kwargs["page"])
        timestamp = int(time.time())
        return {
            "page": page,
            "page_url": "{}{}#document/p{}".format(
                settings.DOCCLOUD_EMBED_URL, document.get_absolute_url(), page
            ),
            "img_url": "{}?ts={}".format(
                page_image_path(document.pk, document.slug, page - 1, "xlarge"),
                timestamp,
            ),
            "text_url": "{}?ts={}".format(
                page_text_path(document.pk, document.slug, page - 1), timestamp
            ),
            "user_org_string": f"{document.user.name} ({document.organization})",
            "app_url": settings.DOCCLOUD_URL,
            "enhance_src": f"{settings.DOCCLOUD_URL}/embed/enhance.js",
            **extra,
        }


@register
class NoteOEmbed(RichOEmbed):
    template = "oembed/note.html"
    patterns = [
        re.compile(
            rf"^{settings.DOCCLOUD_URL}/documents/(?P<doc_pk>[0-9]+)[a-z0-9_-]*/?"
            r"#document/p(?P<page>[0-9]+)/a(?P<pk>[0-9]+)$"
        )
    ]
    width = 750

    def response(self, request, query, max_width=None, max_height=None, **kwargs):
        document = get_object_or_404(
            Document.objects.get_viewable(request.user), pk=kwargs["doc_pk"]
        )
        note = get_object_or_404(
            document.notes.get_viewable(request.user), pk=kwargs["pk"]
        )

        height = None
        if max_width and max_width < self.width:
            width = max_width
        else:
            width = self.width
        oembed = {"title": note.title, "width": width, "height": height}
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
