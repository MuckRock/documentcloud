# Django
from django.db import models
from django.db.models import Q, UniqueConstraint
from django.utils.translation import gettext_lazy as _

# Standard Library
import logging

# DocumentCloud
from documentcloud.documents.choices import EntityKind

logger = logging.getLogger(__name__)


def format_date(date):
    if date is None:
        return None
    return date.replace(tzinfo=None).isoformat() + "Z"


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
        related_name="legacy_entities_2",
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
