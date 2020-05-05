"""
Total documents
- broken down by access
Total pages
- broken down by access
Total notes
- broken down by access
Total projects
"""

# Django
from django.db import models
from django.utils.translation import ugettext_lazy as _


class Statistics(models.Model):
    """Nightly statistics"""

    # pylint: disable=invalid-name
    date = models.DateField(
        unique=True, help_text=_("The date these statistics were taken")
    )

    total_documents = models.IntegerField(help_text=_("The total number of documents"))
    total_documents_public = models.IntegerField(
        help_text=_("The total number of public documents")
    )
    total_documents_organization = models.IntegerField(
        help_text=_("The total number of organizational documents")
    )
    total_documents_private = models.IntegerField(
        help_text=_("The total number of private documents")
    )
    total_documents_invisible = models.IntegerField(
        help_text=_("The total number of invisible documents")
    )
    total_pages = models.IntegerField(help_text=_("The total number of pages"))
    total_pages_public = models.IntegerField(
        help_text=_("The total number of public pages")
    )
    total_pages_organization = models.IntegerField(
        help_text=_("The total number of organizational pages")
    )
    total_pages_private = models.IntegerField(
        help_text=_("The total number of private pages")
    )
    total_pages_invisible = models.IntegerField(
        help_text=_("The total number of invisible pages")
    )
    total_notes = models.IntegerField(help_text=_("The total number of notes"))
    total_notes_public = models.IntegerField(
        help_text=_("The total number of public notes")
    )
    total_notes_organization = models.IntegerField(
        help_text=_("The total number of organizational notes")
    )
    total_notes_private = models.IntegerField(
        help_text=_("The total number of private notes")
    )
    total_notes_invisible = models.IntegerField(
        help_text=_("The total number of invisible notes")
    )
    total_projects = models.IntegerField(help_text=_("The total number of projects"))

    def __str__(self):
        return f"Stats for {self.date}"

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "statistics"
