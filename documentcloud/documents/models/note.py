# Django
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

# DocumentCloud
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.core.utils import format_date
from documentcloud.documents.choices import Access
from documentcloud.documents.querysets import NoteQuerySet


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
    solr_dirty = models.BooleanField(
        _("solr dirty"),
        default=True,
        help_text=_("Tracks if the Solr Index is out of date with the SQL model"),
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

    def save(self, *args, **kwargs):
        """Mark this model's solr index as being out of date on every save"""
        self.solr_dirty = True
        super().save(*args, **kwargs)

    def solr(self):
        """Get a solr document to index this note"""
        return {
            "id": self.pk,
            "document_s": self.document_id,
            "type": "note",
            "user": self.user_id,
            "organization": self.organization_id,
            "access": Access.attributes[self.access],
            "page_count": self.page_number,
            "title": self.title,
            "description": self.content,
            "created_at": format_date(self.created_at),
            "updated_at": format_date(self.updated_at),
            "x1_f": self.x1,
            "x2_f": self.x2,
            "y1_f": self.y1,
            "y2_f": self.y2,
        }
