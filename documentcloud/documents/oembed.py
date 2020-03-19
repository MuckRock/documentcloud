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


@register
class DocumentOEmbed(RichOEmbed):
    patterns = [
        # viewer url
        re.compile(rf"{settings.DOCCLOUD_URL}/documents/(?P<pk>[0-9]+)/?"),
        # api url
        re.compile(rf"{settings.DOCCLOUD_API_URL}/api/documents/(?P<pk>[0-9]+)/?"),
    ]

    def response(self, request, query, max_width=None, max_height=None, **kwargs):
        document = get_object_or_404(
            Document.objects.get_viewable(request.user), pk=kwargs["pk"]
        )

        width, height = self.get_dimensions(
            document.aspect_ratio, max_width, max_height
        )
        oembed = {"title": document.title, "width": width, "height": height}
        template = get_template("oembed/document.html")
        src = settings.DOCCLOUD_EMBED_URL + document.get_absolute_url()
        if query:
            src = f"{src}?{query}"
        oembed["html"] = template.render({"src": src, **oembed})
        return self.oembed(**oembed)

    def get_dimensions(self, aspect_ratio, max_width, max_height):
        default_width = 700
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
