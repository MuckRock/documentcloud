# Third Party
from wikidata.client import Client


class EasyWikidataEntity:
    client = None

    def __init__(self, wikidata_id):
        if not self.client:
            self.client = Client()
        # TODO: Handle 404
        self.entity = self.client.get(wikidata_id, load=True)

    def get_raw_wikidata_entity(self):
        return self.entity

    def get_urls(self):
        return self.entity.data.get("sitelinks")

    def get_names(self):
        return self.entity.label.texts

    def get_description(self):
        return self.entity.description.texts
