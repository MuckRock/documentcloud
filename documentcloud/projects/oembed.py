# Django
from django.conf import settings
from django.template.loader import get_template
from rest_framework.generics import get_object_or_404

# Standard Library
import re

# DocumentCloud
from documentcloud.projects.models import Project
from documentcloud.oembed.oembed import RichOEmbed
from documentcloud.oembed.registry import register


@register
class ProjectOEmbed(RichOEmbed):
    template = "oembed/project.html"
    patterns = [
        # manager url
        re.compile(
            rf"^{settings.DOCCLOUD_URL}/projects/[\w-]*?(?P<proj_pk>[0-9]+)(/|\?|$)"
        ),
        # api url
        re.compile(
            rf"^{settings.DOCCLOUD_API_URL}/api/projects/[\w-]*?(?P<proj_pk>[0-9]+)(/|\?|$)$"
        ),
    ]
    width = 500
    height = 500

    def response(self, request, query, max_width=None, max_height=None, **kwargs):
        project = get_object_or_404(
            Project.objects.get_viewable(request.user), pk=kwargs["proj_pk"]
        )

        if max_width and max_width < self.width:
            width = max_width
        else:
            width = self.width
        if max_height and max_height < self.height:
            height = max_height
        else:
            height = self.height
        oembed = {"title": project.title, "width": width, "height": height}
        context = self.get_context(project, query, oembed, **kwargs)
        template = get_template(self.template)
        oembed["html"] = template.render(context)
        return self.oembed(**oembed)

    def get_context(self, project, query, extra, **kwargs):
        # pylint: disable=unused-argument
        src = settings.DOCCLOUD_EMBED_URL + project.get_absolute_url()
        if query:
            src = f"{src}?{query}"
        return {"src": src, **extra}
