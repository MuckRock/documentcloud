# Django
from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.db import models, transaction
from django.utils.translation import ugettext_lazy as _

# Third Party
from autoslug.fields import AutoSlugField

# DocumentCloud
from documentcloud.common import path
from documentcloud.common.environment import storage
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
        default=Status.nofile,
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
    page_spec = models.TextField(
        _("page specification"),
        blank=True,
        help_text=_("A cached and compressed specification of each pages dimensions"),
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

    data = JSONField(default=dict)

    class Meta:
        permissions = (
            (
                "process_document",
                "Document processor - can set `page_count`, `page_spec`, and "
                "`status` through the API",
            ),
        )

    def __str__(self):
        return self.title

    @property
    def path(self):
        """The path where this documents files are located"""
        return path.path(self.pk)

    @property
    def doc_path(self):
        """The path to the document file"""
        return path.doc_path(self.pk, self.slug)

    @property
    def pages_path(self):
        """The path to the pages directory"""
        return path.pages_path(self.pk)

    @property
    def public(self):
        return self.access == Access.public and self.status in (
            Status.success,
            Status.readable,
        )

    @property
    def asset_url(self):
        if self.public:
            return settings.PUBLIC_ASSET_URL
        else:
            return settings.PRIVATE_ASSET_URL

    def get_page_text(self, page_number):
        try:
            return (
                storage.open(
                    f"{settings.DOCUMENT_BUCKET}/{self.pk}/pages/"
                    f"{self.slug}-p{page_number}.txt",
                    "rb",
                )
                .read()
                .decode("utf8")
            )
        except ValueError:
            return ""

    def solr(self):
        project_ids = [p.pk for p in self.projects.all()]
        pages = {
            f"page_no_{i}": self.get_page_text(i) for i in range(1, self.page_count + 1)
        }
        return {
            "id": self.pk,
            "user": self.user_id,
            "organization": self.organization_id,
            "access": self.get_access_display().lower(),
            "status": self.get_status_display().lower(),
            "title": self.title,
            "slug": self.slug,
            "source": self.source,
            "description": self.description,
            "language": self.language,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "page_count": self.page_count,
            "projects": project_ids,
            **pages,
        }


class DocumentError(models.Model):
    """An error occured while processing a document"""

    document = models.ForeignKey(
        verbose_name=_("document"),
        to="documents.Document",
        on_delete=models.CASCADE,
        related_name="errors",
        help_text=_("The document this page belongs to"),
    )
    created_at = AutoCreatedField(
        _("created at"), help_text=_("Timestamp of when the error occured")
    )
    message = models.TextField(_("message"), help_text=_("The error message"))

    def __str__(self):
        return self.message


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
