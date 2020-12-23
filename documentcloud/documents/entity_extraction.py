# Django
from django.conf import settings
from django.db import transaction

# Standard Library
import logging
from bisect import bisect

# Third Party
import requests
from google.cloud import language_v1
from google.cloud.language_v1.types.language_service import AnalyzeEntitiesResponse

# DocumentCloud
from documentcloud.documents.models import Entity, EntityOccurrence

BYTE_LIMIT = 1000000

logger = logging.getLogger(__name__)


def get_name_from_mid(mid):
    """Use the Google Knowledge Graph API to get the name for the mid"""
    service_url = "https://kgsearch.googleapis.com/v1/entities:search"
    params = {"limit": 1, "key": settings.GOOGLE_API_KEY, "ids": mid}
    response = requests.get(service_url, params=params)
    try:
        return response.json()["itemListElement"][0]["result"]["name"]
    except (IndexError, KeyError):
        return None


class EntityExtractor:
    def __init__(self):
        self.client = language_v1.LanguageServiceClient()
        self.page_map = []

    def _transform_mentions(self, mentions, character_offset):
        """Format mentions how we want to store them in our database
        Rename and flatten some fields and calculate page and page offset
        """
        occurrences = []
        for mention in mentions:
            occurrence = {}
            occurrence["content"] = mention["text"]["content"]
            occurrence["kind"] = mention["type_"]

            offset = mention["text"]["begin_offset"] + character_offset
            page = bisect(self.page_map, offset) - 1
            page_offset = offset - self.page_map[page]

            occurrence["offset"] = offset
            occurrence["page"] = page
            occurrence["page_offset"] = page_offset

            occurrences.append(occurrence)
        return occurrences

    def _extract_entities_text(self, document, text, character_offset):
        """Extract the entities from a given chunk of text from the document"""
        language_document = language_v1.Document(
            content=text, type_=language_v1.Document.Type.PLAIN_TEXT
        )
        logger.info("Calling entity extraction API")
        response = self.client.analyze_entities(
            document=language_document, encoding_type="UTF32"
        )
        logger.info("Converting response to dictionary representation")
        entities = AnalyzeEntitiesResponse.to_dict(response)["entities"]
        occurrence_objs = []
        logger.info("Creating %d entities", len(entities))

        # XXX collapase occurrences of the same entity?

        for entity in entities:
            if "mid" in entity["metadata"]:
                name = get_name_from_mid(entity["metadata"]["mid"])
                if name is not None:
                    entity["name"] = name

        names = [e["name"] for e in entities]
        entity_map = {e.name: e for e in Entity.objects.filter(name__in=names)}
        entity_objs = []
        logger.info("Create entity objects")
        for entity in entities:
            if entity["name"] not in entity_map:
                mid = entity["metadata"].pop("mid", "")
                wikipedia_url = entity["metadata"].pop("wikipedia_url", "")
                entity_obj = Entity(
                    name=entity["name"],
                    kind=entity["type_"],
                    mid=mid,
                    wikipedia_url=wikipedia_url,
                    metadata=entity["metadata"],
                )
                entity_map[entity["name"]] = entity_obj
                entity_objs.append(entity_obj)
        logger.info("Insert entities into the database")
        Entity.objects.bulk_create(entity_objs)

        logger.info("Create entity occurrence objects")
        for entity in entities:
            entity_obj = entity_map[entity["name"]]
            occurrences = self._transform_mentions(entity["mentions"], character_offset)
            occurrence_objs.append(
                EntityOccurrence(
                    document=document,
                    entity=entity_obj,
                    relevance=entity["salience"],
                    occurrences=occurrences,
                )
            )
        logger.info("Insert entity occurrences into the database")
        EntityOccurrence.objects.bulk_create(occurrence_objs)

    @transaction.atomic
    def extract_entities(self, document):
        """Extract the entities from a document"""
        # XXX ensure no entities yet? or clear existing?
        # XXX should document be readable/pending while extracting?
        # XXX what to do about redactions/page edits post entity extraction?

        all_page_text = document.get_all_page_text()
        texts = []
        total_bytes = 0
        self.page_map = [0]
        character_offset = 0
        total_characters = 0

        logger.info(
            "Extracting entities for %s, %d pages",
            document,
            len(all_page_text["pages"]),
        )

        for page in all_page_text["pages"]:
            # page map is stored in unicode characters
            # we add the current page's length in characters to the beginning of the
            # last page, to get the start character of the next page
            page_chars = len(page["contents"])
            self.page_map.append(self.page_map[-1] + page_chars)
            # the API limit is based on byte size, so we use the length of the
            # content encoded into utf8
            page_bytes = len(page["contents"].encode("utf8"))
            if page_bytes > BYTE_LIMIT:
                logger.error("Single page too long for entity extraction")
                return

            if total_bytes + page_bytes > BYTE_LIMIT:
                # if adding another page would put us over the limit,
                # send the current chunk of text to be analyzed
                logger.info("Extracting to page %d", page["page"])
                self._extract_entities_text(document, "".join(texts), character_offset)
                character_offset = total_characters
                texts = [page["contents"]]
                total_bytes = page_bytes
                total_characters += page_chars
            else:
                # otherwise append the current page and accumulate the length
                texts.append(page["contents"])
                total_bytes += page_bytes
                total_characters += page_chars

        # analyze the remaining text
        logger.info("Extracting to end")
        self._extract_entities_text(document, "".join(texts), character_offset)

        logger.info("Extracting entities for %s finished", document)
