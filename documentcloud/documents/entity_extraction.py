# Django
from django.conf import settings
from django.db import transaction
from django.db.models import Q

# Standard Library
import logging
import operator
from bisect import bisect
from functools import reduce
from itertools import zip_longest

# Third Party
import requests
from google.cloud import language_v1
from google.cloud.language_v1.types.language_service import AnalyzeEntitiesResponse

# DocumentCloud
from documentcloud.documents.choices import EntityKind, Status
from documentcloud.documents.models import Entity, EntityOccurrence

BYTE_LIMIT = 1000000

logger = logging.getLogger(__name__)


def grouper(iterable, num, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * num
    return zip_longest(*args, fillvalue=fillvalue)


def get_mid_info(mids):
    """Use the Google Knowledge Graph API to get the name and description for
    all of the given mids"""
    service_url = "https://kgsearch.googleapis.com/v1/entities:search"
    info = {}
    # do 100 mids at a time
    for group in grouper(mids, 100):
        params = {"limit": len(group), "key": settings.GOOGLE_API_KEY, "ids": group}
        response = requests.get(service_url, params=params)
        info.update(
            {
                i["result"]["@id"][3:]: (
                    i["result"].get("name"),
                    i["result"]
                    .get("detailedDescription", {})
                    .get("articleBody", i["result"].get("description")),
                )
                for i in response.json()["itemListElement"]
            }
        )
    return info


def _get_or_create_entities(entities, entity_filter, keyer, mapper):
    """Generic code to generate entities for both those with or without an mid"""

    entities = [e for e in entities if entity_filter(e)]
    keys = [keyer(e) for e in entities]
    entity_map = mapper(keys)

    entity_objs = []
    logger.info("Create entity objects")

    for entity in entities:
        key = keyer(entity)
        if key not in entity_map:
            metadata = entity["metadata"].copy()
            mid = metadata.pop("mid", "")
            wikipedia_url = metadata.pop("wikipedia_url", "")
            entity_obj = Entity(
                name=entity["name"],
                kind=entity["type_"],
                description=entity.get("description", ""),
                mid=mid,
                wikipedia_url=wikipedia_url,
                metadata=metadata,
            )
            entity_map[key] = entity_obj
            entity_objs.append(entity_obj)

    return entity_objs, entity_map


def get_or_create_entities(entities):
    """Get or create the API entities from the database"""

    entity_objs, entity_map = _get_or_create_entities(
        entities,
        lambda e: "mid" in e["metadata"],
        lambda e: e["metadata"]["mid"],
        lambda mids: {e.mid: e for e in Entity.objects.filter(mid__in=mids)},
    )
    entity_objs_, entity_map_ = _get_or_create_entities(
        entities,
        lambda e: "mid" not in e["metadata"],
        lambda e: (e["name"], e["type_"]),
        lambda name_kinds: {
            (e.name, e.kind): e
            for e in Entity.objects.filter(
                reduce(
                    operator.or_, (Q(name=name, kind=kind) for name, kind in name_kinds)
                )
            )
        },
    )
    entity_objs.extend(entity_objs_)
    entity_map.update(entity_map_)

    logger.info("Insert entities into the database")
    # XXX race condition if created between checking and creating
    Entity.objects.bulk_create(entity_objs)
    return entity_map


class EntityExtractor:
    # XXX remove class/refactor
    def __init__(self):
        self.client = language_v1.LanguageServiceClient()
        self.page_map = []

    def _transform_mentions(self, mentions):
        """Format mentions how we want to store them in our database
        Rename and flatten some fields and calculate page and page offset
        """
        occurrences = []
        for mention in mentions:
            occurrence = {}
            occurrence["content"] = mention["text"]["content"]
            occurrence["kind"] = mention["type_"]

            offset = mention["text"]["begin_offset"]
            page = bisect(self.page_map, offset) - 1
            page_offset = offset - self.page_map[page]

            occurrence["offset"] = offset
            occurrence["page"] = page
            occurrence["page_offset"] = page_offset

            occurrences.append(occurrence)
        return occurrences

    def _extract_entities_text(self, text, character_offset):
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

        # remove "number" entities
        entities = [e for e in entities if e["type_"] != EntityKind.number]

        # adjust for character offset
        for entity in entities:
            for mention in entity["mentions"]:
                mention["text"]["begin_offset"] += character_offset

        return entities

    def _create_entities(self, entities, document):
        # get name/desc from knowldge graph
        logger.info("Getting data from the knowledge graph")
        mids = [e["metadata"]["mid"] for e in entities if "mid" in e["metadata"]]
        mid_info = get_mid_info(mids)
        for entity in entities:
            if "mid" in entity["metadata"]:
                name, description = mid_info.get(entity["metadata"]["mid"], ("", ""))
                if name:
                    entity["name"] = name
                if description:
                    entity["description"] = description

        logger.info("Creating %d entities", len(entities))
        entity_map = get_or_create_entities(entities)

        logger.info("Collapse entity occurrences")
        collapsed_entities = {}
        for entity in entities:
            if "mid" in entity["metadata"]:
                entity_obj = entity_map[entity["metadata"]["mid"]]
            else:
                entity_obj = entity_map[(entity["name"], entity["type_"])]
            if entity_obj.pk in collapsed_entities:
                collapsed_entities[entity_obj.pk]["mentions"].extend(entity["mentions"])
            else:
                collapsed_entities[entity_obj.pk] = entity

        logger.info("Create entity occurrence objects")
        occurrence_objs = []
        for entity in collapsed_entities.values():
            if "mid" in entity["metadata"]:
                entity_obj = entity_map[entity["metadata"]["mid"]]
            else:
                entity_obj = entity_map[(entity["name"], entity["type_"])]
            occurrences = self._transform_mentions(entity["mentions"])
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

    def extract_entities(self, document):
        """Extract the entities from a document"""
        # XXX what to do about redactions/page edits post entity extraction?
        # delete all entities prior to any destructive edits
        from documentcloud.documents.tasks import solr_index

        try:
            self._extract_entities(document)
        finally:
            with transaction.atomic():
                document.status = Status.success
                document.save()
                transaction.on_commit(
                    lambda: solr_index.delay(
                        document.pk, field_updates={"status": "set"}
                    )
                )
            logger.info("Extracting entities for %s finished", document)

    @transaction.atomic
    def _extract_entities(self, document):
        all_page_text = document.get_all_page_text()
        texts = []
        total_bytes = 0
        self.page_map = [0]
        character_offset = 0
        total_characters = 0
        entities = []

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
                entities.extend(
                    # XXX call the api in parallel
                    # possibly with overlap
                    # check size of entities to pass through redis (use compression)
                    self._extract_entities_text("".join(texts), character_offset)
                )
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
        entities.extend(self._extract_entities_text("".join(texts), character_offset))

        self._create_entities(entities, document)
