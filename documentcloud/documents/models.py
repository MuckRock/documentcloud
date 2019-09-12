# Django
from django.db import models

# Third Party
from autoslug import AutoSlugField

# DocumentCloud
from documentcloud.core.choices import Language
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.querysets import DocumentQuerySet


class Document(models.Model):
    user = models.ForeignKey(
        "users.User", on_delete=models.PROTECT, related_name="documents"
    )
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="documents"
    )
    access = models.IntegerField(choices=Access.choices)
    status = models.IntegerField(choices=Status.choices, default=Status.pending)

    title = models.CharField(max_length=255)
    slug = AutoSlugField(populate_from="title", unique=True)

    language = models.CharField(
        max_length=3,
        choices=Language.choices,
        blank=True,
        help_text="The language of the document.  Will be used to determine what "
        "OCR package to use for files that require OCR processing.",
    )

    source = models.CharField(
        max_length=1000, blank=True, help_text="The source who produced the document"
    )
    description = models.TextField(
        blank=True, help_text="A paragraph of detailed description"
    )
    created_at = AutoCreatedField(blank=True, null=True)
    updated_at = AutoLastModifiedField(blank=True, null=True)

    objects = DocumentQuerySet.as_manager()

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
    document = models.ForeignKey(
        "documents.Document", on_delete=models.CASCADE, related_name="pages"
    )
    page_number = models.IntegerField(db_index=True)
    text = models.TextField()
    aspect_ratio = models.FloatField(blank=True, null=True)

    class Meta:
        ordering = ("document", "page_number")

    def __str__(self):
        return f"Page {self.page_number} of {self.document.title}"
