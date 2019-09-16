# Django
from django.db import models
from django.utils.translation import ugettext_lazy as _

# Third Party
from autoslug import AutoSlugField

# DocumentCloud
from documentcloud.core.choices import Language
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.querysets import DocumentQuerySet


class Document(models.Model):
    """A document uploaded to DocumentCloud"""

    objects = DocumentQuerySet.as_manager()

    user = models.ForeignKey(
        verbose_name=_("user"),
        to="users.User",
        on_delete=models.PROTECT,
        related_name="documents",
        help_text=_("The user who created this document"),
    )
    organization = models.ForeignKey(
        verbose_name=_("organization"),
        to="organizations.Organization",
        on_delete=models.PROTECT,
        related_name="documents",
        help_text=_("The organization this document was created within"),
    )
    access = models.IntegerField(
        _("access"),
        choices=Access.choices,
        help_text=_("Designates who may access this document by default"),
    )
    status = models.IntegerField(
        _("status"),
        choices=Status.choices,
        default=Status.pending,
        help_text=_("The processing status of this document"),
    )

    title = models.CharField(
        _("title"), max_length=255, db_index=True, help_text=_("The document's title")
    )
    slug = AutoSlugField(
        _("slug"),
        populate_from="title",
        help_text=_("A slug for the document which may be used in a URL"),
    )

    page_count = models.IntegerField(
        _("page count"),
        default=0,
        db_index=True,
        help_text=_("Number of pages in this document"),
    )

    language = models.CharField(
        _("language"),
        max_length=3,
        choices=Language.choices,
        blank=True,
        help_text="The language of the document.  Will be used to determine what "
        "OCR package to use for files that require OCR processing.",
    )

    source = models.CharField(
        _("source"),
        max_length=1000,
        blank=True,
        help_text="The source who produced the document",
    )
    description = models.TextField(
        _("description"), blank=True, help_text="A paragraph of detailed description"
    )
    created_at = AutoCreatedField(
        _("created at"),
        db_index=True,
        help_text=_("Timestamp of when the document was created"),
    )
    updated_at = AutoLastModifiedField(
        _("updated at"), help_text=_("Timestamp of when the document was last updated")
    )

    @property
    def thumbnail(self):
        first_page = self.pages.first()
        if first_page is None or first_page.thumbnail_file is None:
            return None
        return first_page.thumbnail_file.url

    @property
    def combined_page_text(self):
        return "".join(p.text for p in self.pages.all())

    def __str__(self):
        return self.title


class Page(models.Model):
    """A single page in a document"""

    document = models.ForeignKey(
        verbose_name=_("document"),
        to="documents.Document",
        on_delete=models.CASCADE,
        related_name="pages",
        help_text=_("The document this page belongs to"),
    )
    page_number = models.IntegerField(
        _("page number"), db_index=True, help_text=_("The page number")
    )
    text = models.TextField(_("text"), help_text=_("The text on this page"))
    aspect_ratio = models.FloatField(
        blank=True, null=True, help_text=_("The aspect ratio for displaying this page")
    )

    class Meta:
        ordering = ("document", "page_number")

    def __str__(self):
        return f"Page {self.page_number} of {self.document.title}"
