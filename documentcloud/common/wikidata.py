# Django
from django.conf import settings

# Third Party
import requests

# DocumentCloud
from documentcloud.documents.entity_extraction import requests_retry_session
from documentcloud.entities.models import EntityTranslation


class WikidataEntities:
    """Use the API directly to allow for more control"""

    # https://www.wikidata.org/w/api.php?action=help&modules=wbgetentities

    url = "https://www.wikidata.org/w/api.php"
    action = "wbgetentities"
    langs = [l["code"] for l in settings.PARLER_LANGUAGES[settings.SITE_ID]]

    def __init__(self, entities):

        if not isinstance(entities, list):
            entities = [entities]
        self.entities = entities

        wikidata_ids = [e.wikidata_id for e in entitiy]
        resp = requests_retry_session().get(
            self.url,
            params={
                "format": "json",
                "action": self.action,
                "ids": "|".join(wikidata_ids),
                "props": "sitelinks/urls|labels|descriptions",
                "languages": "|".join(langs),
                "sitefilter": "|".join([f"{l}wiki" for l in langs]),
            },
        )
        resp.raise_for_status()
        self.data = resp.json()
        if "error" in self.data:
            raise ValueError(self.data["error"]["info"])

    def get_name(self, wikidata_id, lang):
        return self.data["entities"][wikidata_id]["labels"].get(lang, "")

    def get_description(self, wikidata_id, lang):
        return self.data["entities"][wikidata_id]["descriptions"].get(lang, "")

    def get_url(self, wikidata_id, lang):
        return (
            self.data["entities"][wikidata_id]["sitelinks"]
            .get(f"{lang}wiki", {})
            .get("url", "")
        )

    def create_translations(self):
        """
        Create all the translations for the given entities in all active languages
        in one SQL statement
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
