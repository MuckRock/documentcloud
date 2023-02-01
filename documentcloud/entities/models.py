from django.db import models
from wikidata.client import Client


class Entity(models.Model):
    wd_entity = None

    ACCESS_CHOICES = [("Public", 0), ("Private", 1)]
    # reuse access from documents

    # A dictionary with language codes as keys.
    name = models.JSONField()
    wikidata_id = models.CharField(max_length=16)
    # A dictionary with language codes as keys.
    wikipedia_url = models.JSONField()
    owner = models.ForeignKey(
        "users.User", related_name="entities", on_delete=models.CASCADE
    )
    description = models.JSONField()
    # use documents
    created_at = models.DateTimeField(auto_now=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    access = models.CharField(max_length=20, choices=ACCESS_CHOICES, default="Public")

    def save(self, *args, **kwargs):
        if not self.wikidata_id:
            # Unnecessary?
            raise "Missing wikidata_id in entity."

        if not self.wikipedia_url:
            self.wikipedia_url = self.get_url_for_wikidata_id()

        if not self.name:
            self.name = self.get_name_for_wikidata_id()

        if not self.description:
            self.description = self.get_description_for_wikidata_id()

        super().save(*args, **kwargs)

    def get_wikidata_entity(self):
        if not self.wd_entity:
            client = Client()
            self.wd_entity = client.get(self.wikidata_id, load=True)
        return self.wd_entity

    def get_url_for_wikidata_id(self):
        wd_entity = self.get_wikidata_entity()
        # TODO: Use a library that gets this safely.
        return wd_entity.data["sitelinks"]

    def get_name_for_wikidata_id(self):
        return self.get_wikidata_entity().label.texts

    def get_description_for_wikidata_id(self):
        return self.get_wikidata_entity().description.texts
