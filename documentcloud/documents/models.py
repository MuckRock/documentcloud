# Django
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Q, UniqueConstraint
from django.utils.translation import gettext_lazy as _

# Standard Library
import json
import logging
import sys
import uuid

# Third Party
import boto3
import requests
from listcrunch import uncrunch

# DocumentCloud
from documentcloud.common import path
from documentcloud.common.environment import storage
from documentcloud.core.choices import Language
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.core.utils import slugify
from documentcloud.documents.choices import Access, EntityKind, Status
from documentcloud.documents.querysets import DocumentQuerySet, NoteQuerySet

logger = logging.getLogger(__name__)


def format_date(date):
    if date is None:
        return None
    return date.replace(tzinfo=None).isoformat() + "Z"


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
    slug = models.SlugField(
        _("slug"),
        max_length=255,
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
        max_length=8,
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

    solr_dirty = models.BooleanField(
        _("solr dirty"),
        default=True,
        help_text=_("Tracks if the Solr Index is out of date with the SQL model"),
    )

    data = models.JSONField(default=dict)

    related_article = models.URLField(
        _("related article"),
        blank=True,
        max_length=1024,
        help_text=_("Article this document pertains to"),
    )
    published_url = models.URLField(
        _("published url"),
        blank=True,
        max_length=1024,
        help_text=_("URL where this article is embedded"),
    )
    detected_remote_url = models.URLField(
        _("detected remote url"),
        blank=True,
        max_length=1024,
        help_text=_("Automatically detected URL where this article is embedded"),
    )

    file_hash = models.CharField(
        _("file hash"),
        blank=True,
        max_length=40,
        help_text=_("SHA1 digest of the file contents"),
    )

    original_extension = models.CharField(
        _("original extension"),
        default="pdf",
        max_length=255,
        help_text=_("The original extension of the underlying file"),
    )

    publication_date = models.DateField(
        _("publication date"),
        blank=True,
        null=True,
        help_text=_("Date the document was first made public"),
    )
    publish_at = models.DateTimeField(
        _("publish at"),
        blank=True,
        null=True,
        db_index=True,
        help_text=_("Scheduled time to make document public"),
    )
    cache_dirty = models.BooleanField(
        _("cache dirty"),
        default=False,
        help_text=_(
            "A destructive operation is taking place and the CDN cache for this "
            "document should be invalidated when it is done processing"
        ),
    )

    # legacy fields

    calais_id = models.CharField(
        _("calais id"), max_length=40, blank=True, help_text=_("Open Calais identifier")
    )

    text_changed = models.BooleanField(
        _("text changed"), default=False, help_text=_("User manually changed the text")
    )
    hit_count = models.PositiveIntegerField(
        _("hit count"),
        default=0,
        help_text=_("Number of times this document has been viewed"),
    )
    public_note_count = models.PositiveIntegerField(
        _("public note count"),
        default=0,
        help_text=_("Number of public notes on this document"),
    )
    file_size = models.PositiveIntegerField(
        _("file size"), default=0, help_text=_("The size of the underlying file")
    )
    char_count = models.PositiveIntegerField(
        _("character count"),
        default=0,
        help_text=_("The number of characters in the document"),
    )

    class Meta:
        ordering = ("created_at",)
        permissions = (
            (
                "share_document",
                "Can share edit access to the document through a project",
            ),
            (
                "process_document",
                "Document processor - can set `page_count`, `page_spec`, and "
                "`status` through the API",
            ),
            (
                "change_ownership_document",
                "Can change the user or organization which owns the document",
            ),
        )

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f"/documents/{self.pk}-{self.slug}/"

    def save(self, *args, **kwargs):
        """Mark this model's solr index as being out of date on every save"""
        # pylint: disable=signature-differs
        if not self.slug:
            self.slug = slugify(self.title)
        self.solr_dirty = True
        super().save(*args, **kwargs)

    @transaction.atomic
    def destroy(self):
        from documentcloud.documents.tasks import delete_document_files, solr_delete

        self.status = Status.deleted
        self.save()
        DeletedDocument.objects.create(pk=self.pk)
        transaction.on_commit(lambda: delete_document_files.delay(self.path))
        transaction.on_commit(lambda: solr_delete.delay(self.pk))

    @property
    def path(self):
        """The path where this documents files are located"""
        return path.path(self.pk)

    @property
    def doc_path(self):
        """The path to the document file"""
        return path.doc_path(self.pk, self.slug)

    @property
    def original_path(self):
        """The path to the document before PDF conversion"""
        if self.original_extension == "pdf":
            return self.doc_path
        return path.original_path(self.pk, self.slug, self.original_extension)

    @property
    def public(self):
        return self.access == Access.public and self.status in (
            Status.success,
            Status.readable,
        )

    @property
    def processing(self):
        return self.status in (Status.pending, Status.readable)

    @property
    def asset_url(self):
        if self.public:
            return settings.PUBLIC_ASSET_URL
        else:
            return settings.PRIVATE_ASSET_URL

    @property
    def aspect_ratio(self):
        """Return the aspect ratio of the first page"""
        return self.page_aspect_ratio(0)

    def page_aspect_ratio(self, page):
        """Return the aspect ratio for a given page"""
        default = 0.77
        if not self.page_spec:
            return default

        try:
            dimensions = uncrunch(self.page_spec)[page]
        except (ValueError, KeyError):
            return default

        width, height = [float(d) for d in dimensions.split("x")]

        return width / height

    def get_page_text(self, page_number):
        try:
            return (
                storage.open(path.page_text_path(self.pk, self.slug, page_number), "rb")
                .read()
                .decode("utf8")
            )
        except ValueError as exc:
            logger.error(
                "Error getting page text: Document: %d Page: %d Exception: %s",
                self.pk,
                page_number,
                exc,
                exc_info=sys.exc_info(),
            )
            return ""

    def get_text(self):
        try:
            return (
                storage.open(path.text_path(self.pk, self.slug), "rb")
                .read()
                .decode("utf8")
            )
        except ValueError as exc:
            logger.error(
                "Error getting text: Document: %d Exception: %s",
                self.pk,
                exc,
                exc_info=sys.exc_info(),
            )
            return ""

    def get_all_page_text(self):
        try:
            return json.loads(
                storage.open(path.json_text_path(self.pk, self.slug), "rb")
                .read()
                .decode("utf8")
            )
        except ValueError as exc:
            logger.error(
                "Error getting all page text: Document: %d Exception: %s",
                self.pk,
                exc,
                exc_info=sys.exc_info(),
            )
            return {"pages": [], "updated": None}

    def solr(self, fields=None, index_text=False):
        """Get a solr document to index the current document

        fields is a sequence of field names to restrict indexing to
        This is useful when the document has already been indexed, and you just
        need to update a subset of fields

        if index_text is True, fetch all of the page text to index
        index_text may also be set to the page text data if it has been
        pre-fetched
        """
        if index_text is True:
            page_text = self.get_all_page_text()
        elif isinstance(index_text, dict):
            page_text = index_text

        if index_text:
            pages = {
                f"page_no_{i}": p["contents"]
                for i, p in enumerate(page_text["pages"], start=1)
            }
        else:
            # do not get page text for a partial update, as it is slow and
            # not needed
            pages = {}
        project_memberships = self.projectmembership_set.all()
        project_ids = [p.project_id for p in project_memberships]
        project_edit_access_ids = [
            p.project_id for p in project_memberships if p.edit_access
        ]
        data = {f"data_{key}": values for key, values in self.data.items()}
        notes = [note.solr() for note in self.notes.all()]

        solr_document = {
            "id": self.pk,
            "type": "document",
            "user": self.user_id,
            "organization": self.organization_id,
            "access": Access.attributes[self.access],
            "status": Status.attributes[self.status],
            "title": self.title,
            "slug": self.slug,
            "source": self.source,
            "description": self.description,
            "language": self.language,
            "created_at": format_date(self.created_at),
            "updated_at": format_date(self.updated_at),
            "page_count": self.page_count,
            "projects": project_ids,
            "projects_edit_access": project_edit_access_ids,
            "original_extension": self.original_extension,
            "file_hash": self.file_hash,
            "related_article": self.related_article,
            "publish_at": format_date(self.publish_at),
            "published_url": self.published_url,
            **pages,
            **data,
        }

        if settings.SOLR_INDEX_NOTES and notes:
            # empty notes field can sometimes cause issues with Solr
            solr_document["notes"] = notes

        if fields:
            # for partial updates, just return the needed fields
            fields = list(fields)
            new_solr_document = {"id": self.pk}
            # always include updated_at
            fields.append("updated_at")
            for field in fields:
                new_solr_document[field] = solr_document.get(field)
            solr_document = new_solr_document

        return solr_document

    def invalidate_cache(self):
        """Invalidate public CDN cache for this document's underlying file"""
        logger.info("Invalidating cache for %s", self.pk)
        doc_path = self.doc_path[self.doc_path.index("/") :]
        distribution_id = settings.CLOUDFRONT_DISTRIBUTION_ID
        if distribution_id:
            # we want the doc path without the s3 bucket name
            cloudfront = boto3.client("cloudfront")
            cloudfront.create_invalidation(
                DistributionId=distribution_id,
                InvalidationBatch={
                    "Paths": {"Quantity": 1, "Items": [doc_path]},
                    "CallerReference": str(uuid.uuid4()),
                },
            )
        cloudflare_email = settings.CLOUDFLARE_API_EMAIL
        cloudflare_key = settings.CLOUDFLARE_API_KEY
        cloudflare_zone = settings.CLOUDFLARE_API_ZONE
        url = settings.PUBLIC_ASSET_URL + doc_path[1:]
        if cloudflare_zone:
            requests.post(
                "https://api.cloudflare.com/client/v4/zones/"
                f"{cloudflare_zone}/purge_cache",
                json={"files": [url]},
                headers={
                    "X-Auth-Email": cloudflare_email,
                    "X-Auth-Key": cloudflare_key,
                },
            )


class DeletedDocument(models.Model):
    """If a document is deleted, keep track of it here"""

    id = models.IntegerField(
        _("id"),
        primary_key=True,
        help_text=_("The ID of the document that was deleted"),
    )
    created_at = AutoCreatedField(
        _("created at"),
        db_index=True,
        help_text=_("Timestamp of when the document was deleted"),
    )

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        return str(self.pk)


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

    class Meta:
        ordering = ("document", "created_at")

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
    page_number = models.PositiveIntegerField(
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
        # This is set to false so we can import notes
        # which are made by users who haven't been imported yet
        # Once migration from old DocumentCloud is complete, this should
        # be set back to True
        db_constraint=False,
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
    content = models.TextField(
        _("content"), blank=True, help_text=_("The contents of the note")
    )
    x1 = models.FloatField(
        _("x1"),
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text=_(
            "The left-most coordinate of the note in percantage of the page size"
        ),
    )
    x2 = models.FloatField(
        _("x2"),
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text=_(
            "The right-most coordinate of the note in percantage of the page size"
        ),
    )
    y1 = models.FloatField(
        _("y1"),
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text=_(
            "The top-most coordinate of the note in percantage of the page size"
        ),
    )
    y2 = models.FloatField(
        _("y2"),
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text=_(
            "The bottom-most coordinate of the note in percantage of the page size"
        ),
    )
    created_at = AutoCreatedField(
        _("created at"), help_text=_("Timestamp of when the note was created")
    )
    updated_at = AutoLastModifiedField(
        _("updated at"), help_text=_("Timestamp of when the note was last updated")
    )

    class Meta:
        ordering = ("document", "page_number")

    def detach(self):
        """Turns the note into a page note and places at page 0"""
        self.page_number = 0
        self.x1 = None
        self.x2 = None
        self.y1 = None
        self.y2 = None

    def rotate(self, rotation_amount):
        """Rotates the note by the specified amount"""
        # rotation_amount % 4:
        #   0 -> unchanged
        #   1 -> clockwise
        #   2 -> halfway
        #   3 -> counter-clockwise
        rotation_amount = rotation_amount % 4
        if rotation_amount == 0:
            return  # unchanged

        # If the note is a page note (no coordinates), rotation has no effect
        if None in (self.x1, self.x2, self.y1, self.y2):
            return

        if rotation_amount == 1:
            self.x1, self.x2, self.y1, self.y2 = (
                (1 - self.y2),
                (1 - self.y1),
                self.x1,
                self.x2,
            )
        elif rotation_amount == 2:
            self.x1, self.x2, self.y1, self.y2 = (
                (1 - self.x2),
                (1 - self.x1),
                (1 - self.y2),
                (1 - self.y1),
            )
        elif rotation_amount == 3:
            self.x1, self.x2, self.y1, self.y2 = (
                self.y1,
                self.y2,
                (1 - self.x2),
                (1 - self.x1),
            )

    def __str__(self):
        return self.title

    def solr(self):
        """Get a solr document to index this note"""
        return {
            "id": f"N{self.id}",
            "type": "note",
            "user": self.user_id,
            "organization": self.organization_id,
            "access": Access.attributes[self.access],
            "page_count": self.page_number,
            "title": self.title,
            "description": self.content,
            "created_at": format_date(self.created_at),
            "updated_at": format_date(self.updated_at),
        }


class Section(models.Model):
    """A section of a document"""

    document = models.ForeignKey(
        verbose_name=_("document"),
        to="documents.Document",
        on_delete=models.CASCADE,
        related_name="sections",
        help_text=_("The document this section belongs to"),
    )
    page_number = models.PositiveIntegerField(
        _("page number"), help_text=_("Which page this section appears on")
    )
    title = models.TextField(_("title"), help_text=_("A title for the section"))

    class Meta:
        ordering = ("document", "page_number")
        unique_together = (("document", "page_number"),)

    def __str__(self):
        return self.title


class LegacyEntity(models.Model):
    """An entity within a document imported from Legacy DocumentCloud"""

    document = models.ForeignKey(
        verbose_name=_("document"),
        to="documents.Document",
        on_delete=models.CASCADE,
        related_name="legacy_entities",
        # This is set to false so we can import entities
        # which are attached to documents which haven't been imported yet
        # Once migration from old DocumentCloud is complete, this should
        # be set back to True
        db_constraint=False,
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

    class Meta:
        ordering = ("document", "-relevance")


class EntityDate(models.Model):
    """A date within a document"""

    document = models.ForeignKey(
        verbose_name=_("document"),
        to="documents.Document",
        on_delete=models.CASCADE,
        related_name="dates",
        # This is set to false so we can import entities
        # which are attached to documents which haven't been imported yet
        # Once migration from old DocumentCloud is complete, this should
        # be set back to True
        db_constraint=False,
        help_text=_("The document this entity belongs to"),
    )
    date = models.DateField(_("date"), help_text=_("The date"))
    occurrences = models.TextField(
        _("occurrences"),
        blank=True,
        help_text=_("Where this entity occurs in the document"),
    )

    class Meta:
        ordering = ("document", "date")
        unique_together = (("document", "date"),)


class Entity(models.Model):
    """An entity which can be referenced within a document"""

    name = models.CharField(
        _("name"), max_length=255, help_text=_("The name of this entity")
    )
    kind = models.IntegerField(
        _("kind"),
        choices=EntityKind.choices,
        help_text=_("Categorization of this entity"),
    )
    mid = models.CharField(
        _("knowledge graph id"),
        max_length=13,
        blank=True,
        help_text=_("The Google Knowledge Graph ID for this entity"),
    )
    description = models.TextField(
        _("description"),
        blank=True,
        help_text=_("Detailed description from Google Knowledge Graph"),
    )
    wikipedia_url = models.URLField(
        _("wikipedia url"),
        blank=True,
        help_text=_("The URL to the Wikipedia entry for this entity"),
    )
    metadata = models.JSONField(
        _("metadata"),
        default=dict,
        help_text=_("Extra data asociated with this entity"),
    )

    class Meta:
        constraints = [
            UniqueConstraint(fields=["mid"], name="unique_mid", condition=~Q(mid="")),
            UniqueConstraint(
                fields=["name", "kind"], name="unique_name_kind", condition=Q(mid="")
            ),
        ]

    def __str__(self):
        return self.name


class EntityOccurrence(models.Model):
    """Where a given entity appears in a given document"""

    document = models.ForeignKey(
        verbose_name=_("document"),
        to="documents.Document",
        on_delete=models.CASCADE,
        related_name="entities",
        help_text=_("The document this entity belongs to"),
    )

    entity = models.ForeignKey(
        verbose_name=_("entity"),
        to="documents.Entity",
        on_delete=models.CASCADE,
        related_name="+",
        help_text=_("The entity which appears in the document"),
    )

    relevance = models.FloatField(
        _("relevance"), default=0.0, help_text=_("The relevance of this entity")
    )

    occurrences = models.JSONField(
        _("occurrences"),
        default=dict,
        help_text=_("Extra data asociated with this entity"),
    )

    class Meta:
        unique_together = [("document", "entity")]

    def __str__(self):
        return self.entity.name
