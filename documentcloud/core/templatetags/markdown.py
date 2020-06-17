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
    extensions = ["markdown.extensions.smarty", "markdown.extensions.tables"]
    return mark_safe(markdown.markdown(text, extensions=extensions))
