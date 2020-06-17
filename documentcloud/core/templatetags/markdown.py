# Django
from django.template import Library
from django.template.defaultfilters import stringfilter
from django.utils.safestring import mark_safe

# Third Party
import markdown

register = Library()


@register.filter(name="markdown")
@stringfilter
def markdown_filter(text):
    """Take the provided markdown-formatted text and convert it to HTML."""
    extensions = [
        # for smart quotes
        "markdown.extensions.smarty",
        # for adding IDs to all headings for intra document linking
        "markdown.extensions.toc",
        # for GitHub flavored markdown
        "mdx_gfm",
    ]
    return mark_safe(
        markdown.markdown(text, extensions=extensions, output_format="html")
    )
