# Django
from django.db import models
from django.utils.translation import gettext_lazy as _

# DocumentCloud
from documentcloud.common.wikidata import EasyWikidataEntity
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField
from documentcloud.entities.choices import EntityAccess


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
        "users.User", related_name="entities", on_delete=models.PROTECT
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

    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        if not self.wikidata_id:
            raise ValueError("Missing wikidata_id in entity.")

        self.access = EntityAccess.public

        if not self.wd_entity:
            self.wd_entity = EasyWikidataEntity(self.wikidata_id)

        if not self.wikipedia_url:
            self.wikipedia_url = self.wd_entity.get_urls()

        if not self.localized_names:
            self.localized_names = self.wd_entity.get_names()
            if not self.localized_names:
                raise ValueError("Wikidata entry has no names.")
                # TODO: Convert error to a log.

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

    def set_wd_entity(self, new_wd_entity):
        self.wd_entity = new_wd_entity
