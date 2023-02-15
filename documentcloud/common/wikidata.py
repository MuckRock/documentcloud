# Third Party
from wikidata.client import Client
from wikidata.entity import EntityState


class EasyWikidataEntity:
    def __init__(self, wikidata_id):
        client = Client()
        self.entity = client.get(wikidata_id, load=True)
        if self.entity.state != EntityState.loaded:
            raise ValueError("Wikidata ID does not exist")

    def get_urls(self):
        return self.entity.data.get("sitelinks")

    def get_names(self):
        return self.entity.label.texts

    def get_description(self):
        return self.entity.description.texts

    def get_values(self):
        localized_name = self.get_names()
        name = localized_name.get("en", next(iter(localized_name.values())))
        return {
            "wikipedia_url": self.get_urls(),
            "localized_names": localized_name,
            "name": name,
            "description": self.get_description(),
        }
