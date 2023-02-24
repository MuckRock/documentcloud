# Django
from django.conf import settings
from django.db.models.query import QuerySet, prefetch_related_objects

# DocumentCloud
from documentcloud.documents.entity_extraction import requests_retry_session
from documentcloud.entities.models import (  # pylint: disable=no-name-in-module
    EntityTranslation,
)


class WikidataEntities:
    """Use the API directly to allow for more control"""

    # https://www.wikidata.org/w/api.php?action=help&modules=wbgetentities

    url = "https://www.wikidata.org/w/api.php"
    action = "wbgetentities"
    langs = [l["code"] for l in settings.PARLER_LANGUAGES[settings.SITE_ID]]

    def __init__(self, entities):

        if not isinstance(entities, (list, QuerySet)):
            entities = [entities]
        self.entities = entities

        wikidata_ids = [e.wikidata_id for e in entities]
        resp = requests_retry_session().get(
            self.url,
            params={
                "format": "json",
                "action": self.action,
                "ids": "|".join(wikidata_ids),
                "props": "sitelinks/urls|labels|descriptions",
                "languages": "|".join(self.langs),
                "sitefilter": "|".join([f"{l}wiki" for l in self.langs]),
            },
        )
        resp.raise_for_status()
        self.data = resp.json()
        if "error" in self.data:
            raise ValueError(self.data["error"]["info"])

    def get_name(self, wikidata_id, lang):
        return (
            self.data["entities"][wikidata_id]["labels"].get(lang, {}).get("value", "")
        )

    def get_description(self, wikidata_id, lang):
        return (
            self.data["entities"][wikidata_id]["descriptions"]
            .get(lang, {})
            .get("value", "")
        )

    def get_url(self, wikidata_id, lang):
        return (
            self.data["entities"][wikidata_id]["sitelinks"]
            .get(f"{lang}wiki", {})
            .get("url", "")
        )

    def create_translations(self):
        """
        Create all the translations for the given entities in all active languages
        in one SQL statement.
        This assumes these are new entities who have not had translations created
        for them yet.
        """
        translations = []
        for entity in self.entities:
            for lang in self.langs:
                translations.append(
                    EntityTranslation(
                        master=entity,
                        language_code=lang,
                        name=self.get_name(entity.wikidata_id, lang),
                        description=self.get_description(entity.wikidata_id, lang),
                        wikipedia_url=self.get_url(entity.wikidata_id, lang),
                    )
                )
        EntityTranslation.objects.bulk_create(translations)

    def update_translations(self):
        """
        Update entities existing translations
        """
        prefetch_related_objects(self.entities, "translations")
        translations = []
        for entity in self.entities:
            for translation in entity.translations.all():
                translation.name = self.get_name(
                    entity.wikidata_id, translation.language_code
                )
                translation.description = self.get_description(
                    entity.wikidata_id, translation.language_code
                )
                translation.wikipedia_url = self.get_url(
                    entity.wikidata_id, translation.language_code
                )
                translations.append(translation)
        EntityTranslation.objects.bulk_update(
            translations, ["name", "description", "wikipedia_url"]
        )
