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

# XXX what to do about redactions/page edits post entity extraction?
# delete all entities prior to any destructive edits


# Utility Functions


def grouper(iterable, num, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * num
    return zip_longest(*args, fillvalue=fillvalue)


# Public Functions


def extract_entities(document):
    """The public entry point to the module.
    The document should be set to Status.readable before this function
    is called on it.
    Mainly a wrapper with error handling to ensure document doesn't get stuck
    in a processing state.
    """
    from documentcloud.documents.tasks import solr_index

    try:
        _extract_entities(document)
    finally:
        with transaction.atomic():
            document.status = Status.success
            document.save()
            transaction.on_commit(
                lambda: solr_index.delay(document.pk, field_updates={"status": "set"})
            )
        logger.info("Extracting entities for %s finished", document)


# Private Functions


@transaction.atomic
def _extract_entities(document):
    """Coordinate the extraction of all of the entities"""
    all_page_text = document.get_all_page_text()
    texts = []
    total_bytes = 0
    page_map = [0]
    character_offset = 0
    total_characters = 0
    entities = []

    logger.info(
        "Extracting entities for %s, %d pages", document, len(all_page_text["pages"])
    )

    for page in all_page_text["pages"]:
        # page map is stored in unicode characters
        # we add the current page's length in characters to the beginning of the
        # last page, to get the start character of the next page
        page_chars = len(page["contents"])
        page_map.append(page_map[-1] + page_chars)
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
                _extract_entities_text("".join(texts), character_offset)
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
    entities.extend(_extract_entities_text("".join(texts), character_offset))

    _create_entity_occurrences(entities, document, page_map)


def _extract_entities_text(text, character_offset):
    """Extract the entities from a given chunk of text from the document"""
    client = language_v1.LanguageServiceClient()
    language_document = language_v1.Document(
        content=text, type_=language_v1.Document.Type.PLAIN_TEXT
    )
    logger.info("Calling entity extraction API")
    response = client.analyze_entities(
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


def _create_entity_occurrences(entities, document, page_map):
    """Create the entity occurrence objects in the database,
    linking the entities to the document
    """
    logger.info("Getting data from the knowledge graph")
    mids = [e["metadata"]["mid"] for e in entities if "mid" in e["metadata"]]
    mid_info = _get_mid_info(mids)
    for entity in entities:
        if "mid" in entity["metadata"]:
            name, description = mid_info.get(entity["metadata"]["mid"], ("", ""))
            if name:
                entity["name"] = name
            if description:
                entity["description"] = description

    logger.info("Creating %d entities", len(entities))
    entity_map = _get_or_create_entities(entities)

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
        occurrences = _transform_mentions(entity["mentions"], page_map)
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


def _get_mid_info(mids):
    """Use the Google Knowledge Graph API to get the name and description for
    all of the given mids"""
    # XXX error handling / retry
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


def _get_or_create_entities(entities):
    """Get or create the entities returned from the API in the database"""

    entity_objs, entity_map = _get_entity_type(
        entities,
        lambda e: "mid" in e["metadata"],
        lambda e: e["metadata"]["mid"],
        lambda mids: {e.mid: e for e in Entity.objects.filter(mid__in=mids)},
    )
    entity_objs_, entity_map_ = _get_entity_type(
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


def _get_entity_type(entities, entity_filter, keyer, mapper):
    """Generic code to fetch entities for both those with or without a mid"""

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


def _transform_mentions(mentions, page_map):
    """Format mentions how we want to store them in our database
    Rename and flatten some fields and calculate page and page offset
    """
    occurrences = []
    for mention in mentions:
        occurrence = {}
        occurrence["content"] = mention["text"]["content"]
        occurrence["kind"] = mention["type_"]

        offset = mention["text"]["begin_offset"]
        page = bisect(page_map, offset) - 1
        page_offset = offset - page_map[page]

        occurrence["offset"] = offset
        occurrence["page"] = page
        occurrence["page_offset"] = page_offset

        occurrences.append(occurrence)
    return occurrences
