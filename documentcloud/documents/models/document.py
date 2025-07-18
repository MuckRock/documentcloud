# Django
from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.db.models.aggregates import Max
from django.utils.translation import gettext_lazy as _

# Standard Library
import json
import logging
import sys
import time
import uuid
from io import BytesIO

# Third Party
import boto3
import pymupdf
import requests
from listcrunch import uncrunch
from pikepdf import Page as PikePage, Pdf, Rectangle

# DocumentCloud
from documentcloud.common import path
from documentcloud.common.environment import storage
from documentcloud.common.extensions import EXTENSIONS
from documentcloud.common.utils import graft_page
from documentcloud.core.choices import Language
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.core.utils import format_date, slugify
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.querysets import DocumentQuerySet

logger = logging.getLogger(__name__)


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
        db_index=True,
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
    delayed_index = models.BooleanField(
        _("delayed index"),
        default=False,
        help_text=_(
            "Do not index the document in Solr immediately - "
            "Wait for it to be batched indexed by the dirty indexer. "
            "Useful when uploading in bulk to not overwhelm the Celery queue."
        ),
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
        choices=[(e, e) for e in EXTENSIONS],
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

    noindex = models.BooleanField(
        _("noindex"),
        default=False,
        help_text=_(
            "Ask search engines and DocumentCloud search to not index this document"
        ),
    )
    admin_noindex = models.BooleanField(
        _("admin noindex"),
        default=False,
        help_text=_(
            "Ask search engines and DocumentCloud search to not index this document "
            "(Admin override)"
        ),
    )

    revision_control = models.BooleanField(
        _("revision control"),
        default=False,
        help_text=_(
            "Enable revision control for this document - a copy of the PDF will "
            "be kept before any destructive action is taken"
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
        ordering = ("pk",)
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
        indexes = [
            models.Index(
                fields=["id"],
                condition=Q(solr_dirty=True) & ~Q(status=Status.deleted),
                name="solr_dirty",
            )
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f"/documents/{self.pk}-{self.slug}/"

    def save(self, *args, **kwargs):
        """Mark this model's solr index as being out of date on every save"""
        if not self.slug:
            self.slug = slugify(self.title)
        self.solr_dirty = True
        super().save(*args, **kwargs)

    @transaction.atomic
    def destroy(self):
        # DocumentCloud
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
        except (ValueError, KeyError, IndexError):
            return default

        width, height = [float(d) for d in dimensions.split("x")]

        return width / height

    def page_size(self, page):
        "Return the width and height of a given page, as a tuple"
        default = (8.5, 11.0)
        if not self.page_spec:
            return default

        try:
            dimensions = uncrunch(self.page_spec)[page]
        except (ValueError, KeyError, IndexError):
            return default

        width, height = [float(d) for d in dimensions.split("x")]

        return (width, height)

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

    def set_page_text(self, page_text_infos):
        logger.info("[SET PAGE TEXT] get all page text %d", self.pk)
        # get the json text
        json_text = self.get_all_page_text()

        # set the individual text pages
        timestamp = int(round(time.time() * 1000))
        json_text["updated"] = timestamp
        if len(json_text["pages"]) < self.page_count:
            json_text["pages"].extend(
                [{} for _ in range(self.page_count - len(json_text["pages"]))]
            )
        file_names = []
        file_contents = []

        logger.info("[SET PAGE TEXT] init graft pdf %d", self.pk)

        positions_present = any("positions" in page for page in page_text_infos)

        for page_text_info in page_text_infos:
            page = page_text_info["page_number"]
            logger.info("[SET PAGE TEXT] %d - page %d", self.pk, page)
            text = page_text_info["text"]
            ocr = page_text_info.get("ocr")
            file_names.append(path.page_text_path(self.pk, self.slug, page))
            file_contents.append(text.encode("utf8"))
            # overwrite the text in the JSON format
            json_text["pages"][page] = {
                "page": page,
                "contents": text,
                "ocr": ocr,
                "updated": timestamp,
            }

        if positions_present:
            doc_contents = self._set_page_positions(
                page_text_infos,
                file_names,
                file_contents,
            )
            if doc_contents is not None:
                # upload grafted pdf
                file_names.append(self.doc_path)
                file_contents.append(doc_contents)

        # set the full text
        concatenated_text = b"\n\n".join(
            [p["contents"].encode("utf-8") for p in json_text["pages"]]
        )
        file_names.append(path.text_path(self.pk, self.slug))
        file_contents.append(concatenated_text)

        # set the json text
        file_names.append(path.json_text_path(self.pk, self.slug))
        file_contents.append(json.dumps(json_text).encode("utf-8"))

        # upload the text to S3
        logger.info(
            "[SET PAGE TEXT] upload %d - %d mb",
            self.pk,
            sum(len(i) for i in file_contents) / 1000 / 1000,
        )
        for name, contents in zip(file_names, file_contents):
            logger.info(
                "[SET PAGE TEXT] upload %d - %s: %d mb",
                self.pk,
                name,
                len(contents) / 1000 / 1000,
            )
        # reverse the lists to upload the larger files first
        storage.async_upload(file_names[::-1], file_contents[::-1], access=self.access)

        return json_text

    def _set_page_positions(self, pages, file_names, file_contents):
        """Handle grafting page positions back into the document"""

        current_pdf = pymupdf.open(stream=storage.open(self.doc_path, "rb").read())
        start_page = pages[0]["page_number"]
        stop_page = pages[-1]["page_number"]

        visible_text = self._check_visible_text(current_pdf, start_page, stop_page)
        logger.info(
            "[SET PAGE TEXT] %d - visible text detected: %s", self.pk, visible_text
        )
        if visible_text:
            # merging when we need to flatten visible text causes excessive memory usage
            return None

        grafted_pdf, base_pdf_stream = self._init_graft_pdf(
            current_pdf,
            start_page,
            stop_page,
            visible_text,
        )

        for page in pages:
            page_number = page["page_number"]
            if page.get("positions"):
                logger.info(
                    "[SET PAGE TEXT] %d - positions page %d", self.pk, page_number
                )
                file_names.append(
                    path.page_text_position_path(self.pk, self.slug, page_number)
                )
                positions = [{**p.pop("metadata", {}), **p} for p in page["positions"]]
                file_contents.append(json.dumps(positions).encode("utf-8"))

                logger.info("[SET PAGE TEXT] %d - graft page %d", self.pk, page_number)
                # create the overlay file
                graft_page(page["positions"], grafted_pdf[page_number - start_page])

        # merge the overlay pages back onto the original document
        if visible_text:
            contents = self._merge_overlay_visible(
                current_pdf,
                grafted_pdf,
                start_page,
                stop_page,
            )
        else:
            contents = self._merge_overlay(
                base_pdf_stream,
                grafted_pdf,
                start_page,
                stop_page,
            )
        current_pdf.close()
        grafted_pdf.close()

        return contents

    def _merge_overlay(self, base_pdf_stream, grafted_pdf, start_page, stop_page):
        """Merge the text only overlay pages back in to the base PDF"""
        base_pdf = Pdf.open(base_pdf_stream)
        overlay_pdf = Pdf.open(BytesIO(grafted_pdf.tobytes()))

        for i in range(start_page, stop_page + 1):
            base_page = PikePage(base_pdf.pages[i])
            overlay_page = PikePage(overlay_pdf.pages[i - start_page])
            base_page.add_overlay(overlay_page, Rectangle(*base_page.trimbox))

        buffer = BytesIO()
        base_pdf.save(buffer)
        buffer.seek(0)
        return buffer.read()

    def _merge_overlay_visible(self, current_pdf, grafted_pdf, start_page, stop_page):
        """Merge the flatten grafted pages back into the PDF"""
        logger.info(
            "[MERGE OVERLAY VISIBLE] %d - start - %d - %d",
            self.pk,
            start_page,
            stop_page,
        )
        current_pdf.delete_pages(start_page, stop_page)
        current_pdf.insert_pdf(grafted_pdf, start_at=start_page)
        logger.info("[MERGE OVERLAY VISIBLE] %d - tobytes", self.pk)
        contents = current_pdf.tobytes(deflate=True, garbage=2, use_objstms=True)
        logger.info("[MERGE OVERLAY VISIBLE] %d - tobytes done", self.pk)
        return contents

    def _check_visible_text(self, current_pdf, start_page, stop_page):
        """Check if the pages contain visible text"""
        for pdf_page in current_pdf.pages(start_page, stop_page + 1):
            text_trace = pdf_page.get_texttrace()
            for trace in text_trace:
                # zero opacity means the text is transparant
                # text type 3 is hidden text
                if trace["opacity"] != 0 and trace["type"] != 3:
                    return True
        return False

    def _init_graft_pdf(self, current_pdf, start_page, stop_page, visible_text):
        """Initialize a new PDF to graft OCR text onto"""
        grafted_pdf = pymupdf.open()
        buffer = BytesIO()

        for pdf_page in current_pdf.pages(start_page, stop_page + 1):
            new_pdf_page = grafted_pdf.new_page(
                width=pdf_page.rect.width,
                height=pdf_page.rect.height,
            )
            if visible_text:
                pdf_pix_map = pdf_page.get_pixmap(dpi=300, colorspace="RGB")
                new_pdf_page.insert_image(rect=pdf_page.rect, pixmap=pdf_pix_map)
            else:
                pdf_page.add_redact_annot(pdf_page.rect)
                pdf_page.apply_redactions(
                    images=pymupdf.PDF_REDACT_IMAGE_NONE,
                    graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                )

        current_pdf.save(buffer)
        return grafted_pdf, buffer

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

        def page_filter(text):
            # S3 returns a null byte at the end of the text file
            text = text.replace("\x00", "")
            # "${" causes some very odd bug to trigger in Solr
            # Punctuation is not indexed anyway, so we will just remove it
            text = text.replace("${", "")
            return text

        if index_text:
            pages = {
                f"page_no_{i}": page_filter(p["contents"])
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
            "page_spec": self.page_spec,
            "projects": project_ids,
            "projects_edit_access": project_edit_access_ids,
            "original_extension": self.original_extension,
            "file_hash": self.file_hash,
            "related_article": self.related_article,
            "publish_at": format_date(self.publish_at),
            "published_url": self.published_url,
            "noindex": self.noindex or self.admin_noindex,
            **pages,
            **data,
        }

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

    def index_on_commit(self, **kwargs):
        """Index the document in Solr on tranasction commit"""
        # DocumentCloud
        from documentcloud.documents.tasks import solr_index

        if not self.delayed_index:
            transaction.on_commit(lambda: solr_index.delay(self.pk, **kwargs))

    def create_revision(self, user_pk, comment, copy=False):
        """Create a new revision"""
        if self.revision_control:
            current_version = self.revisions.aggregate(max=Max("version"))["max"]
            version = 1 if current_version is None else current_version + 1
            revision = self.revisions.create(
                user_id=user_pk,
                version=version,
                comment=comment,
            )
            if copy:
                use_original_extension = comment == "Initial"
                revision.copy(use_original_extension)


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
        related_name="+",
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


class Revision(models.Model):
    """A saved version of the document made before it was edited"""

    document = models.ForeignKey(
        verbose_name=_("document"),
        to="documents.Document",
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    user = models.ForeignKey(
        verbose_name=_("user"),
        to="users.User",
        on_delete=models.PROTECT,
        related_name="revisions",
    )
    created_at = AutoCreatedField(
        _("created at"),
    )
    version = models.PositiveIntegerField(
        _("version"),
        default=0,
    )
    comment = models.CharField(
        _("comment"),
        max_length=255,
    )

    class Meta:
        unique_together = [("document", "version")]
        ordering = ("version",)

    def copy(self, use_original_extension=False):
        """Copy the current document to this revision"""
        if use_original_extension:
            extension = self.document.original_extension
            source = self.document.original_path
        else:
            extension = "pdf"
            source = self.document.doc_path

        destination = path.doc_revision_path(
            self.document.pk, self.document.slug, self.version, extension
        )
        if storage.exists(destination):
            logger.warning(
                "[REVISION] Copy to destination already exists: %s", destination
            )
        else:
            storage.copy(source, destination)
