# Django
from django.db import models
from django.utils.translation import gettext_lazy as _

# Standard Library
import logging

# DocumentCloud
from documentcloud.common.wikidata import EasyWikidataEntity
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.entities.choices import EntityAccess

logger = logging.getLogger(__name__)


class Entity(models.Model):
    wd_entity = None
    # A dictionary with language codes as keys.
    name = models.CharField(max_length=500)
    localized_names = models.JSONField()
    # Unique key?
    wikidata_id = models.CharField(max_length=16, unique=True)
    # A dictionary with language codes as keys.
    wikipedia_url = models.JSONField()
    # Public entities should have a null owner.
    owner = models.ForeignKey(
        "users.User", related_name="entities", on_delete=models.PROTECT, null=True
    )
    description = models.JSONField()
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
        help_text=_("Designates who may access this entity."),
    )

    metadata = models.JSONField(null=True)

    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        if not self.wikidata_id:
            # TODO: Call save_private here instead.
            raise ValueError("Missing wikidata_id in entity.")

        self.access = EntityAccess.public

        self.owner = None

        if not self.wd_entity:
            self.establish_wd_entity(self.wikidata_id)

        if not self.wikipedia_url:
            self.wikipedia_url = self.wd_entity.get_urls()

        if not self.localized_names:
            self.localized_names = self.wd_entity.get_names()
            if not self.localized_names:
                logger.warn("Wikidata entry for %s has no names.", self.wikidata_id)
                raise ValueError("Wikidata entry has no names.")

        # English bias here. TODO: How can this be addressed?
        self.name = self.localized_names.get("en")
        if not self.name:
            if self.localized_names:
                self.name = list(self.localized_names.values())[0]
            else:
                self.name = "Unknown"

        if not self.description:
            self.description = self.wd_entity.get_description()

        super().save(*args, **kwargs)

    def get_wd_entity(self, wikidata_id):
        return EasyWikidataEntity(wikidata_id)

    def establish_wd_entity(self, wikidata_id):
        self.wd_entity = self.get_wd_entity(wikidata_id)


# TODO: Find a better name or replace the old EntityOccurrence
class EntityOccurrence2(models.Model):
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
        help_text=_("Extra data asociated with this entity"),
    )
