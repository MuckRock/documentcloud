# Django
from django.db import models
from django.utils.translation import gettext_lazy as _

# Third Party
from wikidata.client import Client

# DocumentCloud
from documentcloud.core.fields import AutoCreatedField, AutoLastModifiedField

# Local
from documentcloud.entities.choices import EntityAccess


class Entity(models.Model):
    wd_entity = None

    # A dictionary with language codes as keys.
    name = models.CharField(max_length=500)
    localized_names = models.JSONField()
    wikidata_id = models.CharField(max_length=16)
    # A dictionary with language codes as keys.
    wikipedia_url = models.JSONField()
    owner = models.ForeignKey(
        "users.User", related_name="entities", on_delete=models.CASCADE
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

    def save(self, *args, **kwargs):
        if not self.wikidata_id:
            # Unnecessary?
            raise "Missing wikidata_id in entity."

        if not self.wikipedia_url:
            self.wikipedia_url = self.get_url_for_wikidata_id()

        if not self.name or not self.localized_names:
            self.localized_names = self.get_names_for_wikidata_id()
            # English bias here. TODO: How can this be addressed?
            self.name = self.localized_names["en"]
            if not self.name:
                keys = self.localized_names.keys()
                if len(keys) > 0:
                    self.name = self.localized_names[keys[0]]
                else:
                    self.name = "Unknown"

        if not self.description:
            self.description = self.get_description_for_wikidata_id()

        super().save(*args, **kwargs)

    def get_wikidata_entity(self):
        # TODO: Handle 404
        if not self.wd_entity:
            client = Client()
            self.wd_entity = client.get(self.wikidata_id, load=True)
        return self.wd_entity

    def get_url_for_wikidata_id(self):
        wd_entity = self.get_wikidata_entity()
        # TODO: Use a library that gets this safely.
        return wd_entity.data["sitelinks"]

    def get_names_for_wikidata_id(self):
        return self.get_wikidata_entity().label.texts

    def get_description_for_wikidata_id(self):
        return self.get_wikidata_entity().description.texts
