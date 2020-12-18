# Standard Library
import logging
from bisect import bisect

# Third Party
from google.cloud import language_v1
from google.cloud.language_v1.types.language_service import AnalyzeEntitiesResponse

# DocumentCloud
from documentcloud.documents.models import Entity, EntityOccurence

TEXT_LIMIT = 1000000

logger = logging.getLogger(__name__)


class EntityExtractor:
    def __init__(self):
        self.client = language_v1.LanguageServiceClient()
        self.page_map = []

    def _transform_mentions(self, mentions):
        """Format mentions how we want to store them in our database
        Rename and flatten some fields and calculate page and page offset
        """
        occurences = []
        for mention in mentions:
            occurence = {}
            occurence["content"] = mention["text"]["content"]
            occurence["kind"] = mention["type_"]

            offset = mention["text"]["begin_offset"]
            page = bisect(self.page_map, offset) - 1
            page_offset = offset - self.page_map[page]

            occurence["offset"] = offset
            occurence["page"] = page
            occurence["page_offset"] = page_offset

            occurences.append(occurence)
        return occurences

    def _extract_entities_text(self, document, text):
        """Extract the entities from a given chunk of text from the document"""
        language_document = language_v1.Document(
            content=text, type_=language_v1.Document.Type.PLAIN_TEXT
        )
        response = self.client.analyze_entities(
            document=language_document, encoding_type="UTF32"
        )
        entities = AnalyzeEntitiesResponse.to_dict(response)["entities"]
        for entity in entities:
            entity_obj, _created = Entity.objects.get_or_create(
                name=entity["name"],
                defaults={"kind": entity["type_"], "metadata": entity["metadata"]},
            )
            occurences = self._transform_mentions(entity["mentions"])
            EntityOccurence.objects.create(
                document=document,
                entity=entity_obj,
                relevance=entity["salience"],
                occurences=occurences,
            )

    def extract_entities(self, document):
        """Extract the entities from a document"""
        # XXX ensure no entities yet? or clear existing?
        # XXX should document be readable/pending while extracting?
        # XXX what to do about redactions/page edits post entity extraction?

        page_text = document.get_all_page_text()
        texts = []
        total_len = 0
        self.page_map = [0]

        for page in page_text["pages"]:
            # page map is stored in unicode characters
            # we add the current page's length in characters to the beginning of the
            # last page, to get the start character of the next page
            self.page_map.append(self.page_map[-1] + len(page["contents"]))
            # the API limit is based on byte size, so we use the length of the
            # content encoded into utf8
            page_len = len(page["contents"].encode("utf8"))
            if page_len > TEXT_LIMIT:
                logger.error("Single page too long for entity extraction")
                return

            if total_len + page_len > TEXT_LIMIT:
                # if adding another page would put us over the limit,
                # send the current chunk of text to be analyzed
                self._extract_entities_text(document, "".join(texts))
                texts = []
            else:
                # otherwise append the current page and accumulate the length
                texts.append(page["contents"])
                total_len += page_len

        # analyze the remaining text
        self._extract_entities_text(document, "".join(texts))
