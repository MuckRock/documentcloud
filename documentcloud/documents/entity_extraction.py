# Django
from django.db import transaction

# Standard Library
import logging
from bisect import bisect

# Third Party
from google.cloud import language_v1
from google.cloud.language_v1.types.language_service import AnalyzeEntitiesResponse

# DocumentCloud
from documentcloud.documents.models import Entity, EntityOccurence

BYTE_LIMIT = 1000000

logger = logging.getLogger(__name__)


class EntityExtractor:
    def __init__(self):
        self.client = language_v1.LanguageServiceClient()
        self.page_map = []

    def _transform_mentions(self, mentions, character_offset):
        """Format mentions how we want to store them in our database
        Rename and flatten some fields and calculate page and page offset
        """
        occurences = []
        for mention in mentions:
            occurence = {}
            occurence["content"] = mention["text"]["content"]
            occurence["kind"] = mention["type_"]

            offset = mention["text"]["begin_offset"] + character_offset
            page = bisect(self.page_map, offset) - 1
            page_offset = offset - self.page_map[page]

            occurence["offset"] = offset
            occurence["page"] = page
            occurence["page_offset"] = page_offset

            occurences.append(occurence)
        return occurences

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
        occurence_objs = []
        logger.info("Creating %d entities", len(entities))
        # XXX collapase occurences of the same entity?
        names = [e["name"] for e in entities]
        entities = Entity.objects.filter(name__in=names)
        entity_map = {e["name"]: e for e in entities}
        entity_objs = []
        for entity in entities:
            if entity["name"] not in entity_map:
                entity_obj = Entity(
                    name=entity["name"],
                    kind=entity["type_"],
                    metadata=entity["metadata"],
                )
                entity_map[entity["name"]] = entity_obj
                entity_objs.append(entity_obj)
        Entity.objects.bulk_create(entity_objs)

        for entity in entities:
            entity_obj = entity_map[entity["name"]]
            occurences = self._transform_mentions(entity["mentions"], character_offset)
            occurence_objs.append(
                EntityOccurence(
                    document=document,
                    entity=entity_obj,
                    relevance=entity["salience"],
                    occurences=occurences,
                )
            )
        EntityOccurence.objects.bulk_create(occurence_objs)

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
