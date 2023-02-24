# Django
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

# Standard Library
import logging

# Third Party
from parler.models import TranslatableModel, TranslatedFields

# DocumentCloud
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.entities.choices import EntityAccess
from documentcloud.entities.querysets import EntityQuerySet

logger = logging.getLogger(__name__)


class Entity(TranslatableModel):

    objects = EntityQuerySet.as_manager()

    translations = TranslatedFields(
        name=models.CharField(_("name"), max_length=500, blank=True),
        wikipedia_url=models.URLField(_("wikipedia url"), max_length=500, blank=True),
        description=models.TextField(_("description"), blank=True),
    )

    wikidata_id = models.CharField(
        _("wikidata id"), max_length=16, unique=True, blank=True, null=True
    )
    # Public entities should have a null owner.
    user = models.ForeignKey(
        "users.User", related_name="entities", on_delete=models.PROTECT, null=True
    )
    created_at = AutoCreatedField(
        _("created at"),
        db_index=True,
        help_text=_("Timestamp of when the entity was created"),
    )
    updated_at = AutoLastModifiedField(
        _("updated at"), help_text=_("Timestamp of when the entity was last updated")
    )
    access = models.IntegerField(
        _("access"),
        choices=EntityAccess.choices,
        default=EntityAccess.public,
        help_text=_("Designates who may access this entity."),
    )

    metadata = models.JSONField(
        _("metadata"), default=dict, help_text=_("Extra data about this entity")
    )

    class Meta:
        verbose_name_plural = "entities"

    def __str__(self):
        return self.wikidata_id


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
        to="entities.Entity",
        on_delete=models.CASCADE,
        related_name="+",
        help_text=_("The entity which appears in the document"),
    )

    # TODO should we replace this with a metadata field?
    relevance = models.FloatField(
        _("relevance"), default=0.0, help_text=_("The relevance of this entity")
    )

    occurrences = models.JSONField(
        _("occurrences"),
        default=dict,
        help_text=_("Locations of entity in this document"),
    )

    class Meta:
        unique_together = [("document", "entity")]

    def __str__(self):
        return self.entity.name
