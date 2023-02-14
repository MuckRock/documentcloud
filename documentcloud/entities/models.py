# Django
from django.db import models
from django.utils.translation import gettext_lazy as _

# Standard Library
import logging

# DocumentCloud
from documentcloud.common.wikidata import EasyWikidataEntity
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.entities.choices import EntityAccess
from documentcloud.entities.querysets import EntityQuerySet

logger = logging.getLogger(__name__)


class Entity(models.Model):

    objects = EntityQuerySet.as_manager()

    wd_entity = None
    # A dictionary with language codes as keys.
    name = models.CharField(max_length=500, blank=True)
    localized_names = models.JSONField(default=dict)
    # Unique key?
    wikidata_id = models.CharField(max_length=16, unique=True, blank=True, null=True)
    # A dictionary with language codes as keys.
    wikipedia_url = models.JSONField(default=dict)
    # Public entities should have a null owner.
    user = models.ForeignKey(
        "users.User", related_name="entities", on_delete=models.PROTECT, null=True
    )
    description = models.JSONField(default=dict)
    created_at = AutoCreatedField(
        _("created at"),
        db_index=True,
        help_text=_("Timestamp of when the entity was created"),
    )
    updated_at = AutoLastModifiedField(
        _("updated at"), help_text=_("Timestamp of when the entitywas last updated")
    )
    access = models.IntegerField(
        _("access"),
        choices=EntityAccess.choices,
        default=EntityAccess.public,
        help_text=_("Designates who may access this entity."),
    )

    metadata = models.JSONField(
        default=dict, help_text=_("Extra data about this entity")
    )

    def lookup_wikidata(self):
        """Fill in information from Wikidata"""
        if not self.wikidata_id:
            return
        if not self.wd_entity:
            self.wd_entity = EasyWikidataEntity(self.wikidata_id)

        self.wikipedia_url = self.wd_entity.get_urls()
        self.localized_names = self.wd_entity.get_names()
        if not self.localized_names:
            logger.warning("Wikidata entry for %s has no names.", self.wikidata_id)
            # raise ValueError("Wikidata entry has no names.")

        # English bias here. TODO: How can this be addressed?
        self.name = self.localized_names.get("en")
        if not self.name:
            if self.localized_names:
                self.name = list(self.localized_names.values())[0]
            else:
                self.name = "Unknown"

        self.description = self.wd_entity.get_description()


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

    relevance = models.FloatField(
        _("relevance"), default=0.0, help_text=_("The relevance of this entity")
    )

    occurrences = models.JSONField(
        _("occurrences"),
        default=dict,
        help_text=_("Locations of entity in this document"),
    )
