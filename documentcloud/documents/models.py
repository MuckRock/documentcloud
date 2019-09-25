# Django
from django.db import models
from django.utils.translation import ugettext_lazy as _

# Third Party
from autoslug import AutoSlugField

# DocumentCloud
from documentcloud.core.choices import Language
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.querysets import DocumentQuerySet, NoteQuerySet


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
        _("title"), max_length=1000, db_index=True, help_text=_("The document's title")
    )
    slug = AutoSlugField(
        _("slug"),
        max_length=255,
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
        help_text=_(
            "The language of the document.  Will be used to determine what "
            "OCR package to use for files that require OCR processing."
        ),
    )

    source = models.CharField(
        _("source"),
        max_length=1000,
        blank=True,
        help_text=_("The source who produced the document"),
    )
    description = models.TextField(
        _("description"), blank=True, help_text=_("A paragraph of detailed description")
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


class Note(models.Model):
    """A note on a document"""

    objects = NoteQuerySet.as_manager()

    document = models.ForeignKey(
        verbose_name=_("document"),
        to="documents.Document",
        on_delete=models.CASCADE,
        related_name="notes",
        help_text=_("The document this note belongs to"),
    )
    user = models.ForeignKey(
        verbose_name=_("user"),
        to="users.User",
        on_delete=models.PROTECT,
        related_name="notes",
        help_text=_("The user who created this note"),
    )
    organization = models.ForeignKey(
        verbose_name=_("organization"),
        to="organizations.Organization",
        on_delete=models.PROTECT,
        related_name="notes",
        help_text=_("The organization this note was created within"),
    )
    page_number = models.IntegerField(
        _("page number"), help_text=_("Which page this note appears on")
    )
    access = models.IntegerField(
        _("access"),
        choices=Access.choices,
        help_text=_("Designates who may access this document by default"),
    )
    title = models.TextField(_("title"), help_text=_("A title for the note"))
    content = models.TextField(_("content"), help_text=_("The contents of the note"))
    top = models.PositiveSmallIntegerField(
        _("top"),
        null=True,
        blank=True,
        help_text=_("The top coordinate of the note in percantage of the page size"),
    )
    left = models.PositiveSmallIntegerField(
        _("left"),
        null=True,
        blank=True,
        help_text=_("The left coordinate of the note in percantage of the page size"),
    )
    bottom = models.PositiveSmallIntegerField(
        _("bottom"),
        null=True,
        blank=True,
        help_text=_("The bottom coordinate of the note in percantage of the page size"),
    )
    right = models.PositiveSmallIntegerField(
        _("right"),
        null=True,
        blank=True,
        help_text=_("The right coordinate of the note in percantage of the page size"),
    )
    created_at = AutoCreatedField(
        _("created at"), help_text=_("Timestamp of when the note was created")
    )
    updated_at = AutoLastModifiedField(
        _("updated at"), help_text=_("Timestamp of when the note was last updated")
    )

    def __str__(self):
        return self.title


class Section(models.Model):
    """A section of a document"""

    document = models.ForeignKey(
        verbose_name=_("document"),
        to="documents.Document",
        on_delete=models.CASCADE,
        related_name="sections",
        help_text=_("The document this section belongs to"),
    )
    page_number = models.IntegerField(
        _("page number"), help_text=_("Which page this section appears on")
    )
    title = models.TextField(_("title"), help_text=_("A title for the section"))

    def __str__(self):
        return self.title


class Entity(models.Model):
    """An entity within a document"""

    document = models.ForeignKey(
        verbose_name=_("document"),
        to="documents.Document",
        on_delete=models.CASCADE,
        related_name="entities",
        help_text=_("The document this entity belongs to"),
    )
    kind = models.CharField(
        _("kind"),
        max_length=40,
        choices=[
            ("person", "Person"),
            ("organization", "Organization"),
            ("place", "Place"),
            ("term", "Term"),
            ("email", "Email"),
            ("phone", "Phone"),
            ("city", "City"),
            ("state", "State"),
            ("country", "Country"),
        ],
        help_text=_("The kind of entity"),
    )
    value = models.CharField(
        _("value"), max_length=255, help_text=_("The value of this entity")
    )
    relevance = models.FloatField(
        _("relevance"), default=0.0, help_text=_("The relevance of this entity")
    )
    calais_id = models.CharField(
        _("calais id"),
        max_length=40,
        blank=True,
        help_text=_("The ID from open calais"),
    )
    occurrences = models.TextField(
        _("occurrences"),
        blank=True,
        help_text=_("Where this entity occurs in the document"),
    )


class EntityDate(models.Model):
    """A date within a document"""

    document = models.ForeignKey(
        verbose_name=_("document"),
        to="documents.Document",
        on_delete=models.CASCADE,
        related_name="dates",
        help_text=_("The document this entity belongs to"),
    )
    date = models.DateField(_("date"), help_text=_("The date"))
    occurrences = models.TextField(
        _("occurrences"),
        blank=True,
        help_text=_("Where this entity occurs in the document"),
    )

    class Meta:
        unique_together = (("document", "date"),)
