# Third Party
# Standard Library
import logging

from google.cloud import language_v1
from google.cloud.language_v1.types.language_service import AnalyzeEntitiesResponse

# DocumentCloud
from documentcloud.documents.models import Entity, EntityOccurence

TEXT_LIMIT = 1000000

logger = logging.getLogger(__name__)


def _extract_entities_text(document, text):
    client = language_v1.LanguageServiceClient()
    language_document = language_v1.Document(
        content=text, type_=language_v1.Document.Type.PLAIN_TEXT
    )
    response = client.analyze_entities(
        document=language_document, encoding_type="UTF32"
    )
    entities = AnalyzeEntitiesResponse.to_dict(response)["entities"]
    for entity in entities:
        entity_obj, _created = Entity.objects.get_or_create(
            name=entity["name"],
            defaults={"kind": entity["type_"], "metadata": entity["metadata"]},
        )
        EntityOccurence.objects.create(
            document=document,
            entity=entity_obj,
            relevance=entity["salience"],
            occurences=entity["mentions"],
        )


def extract_entities(document):
    """Extract the entities from a document"""
    # XXX ensure no entities yet? or clear existing?

    page_text = document.get_all_page_text()
    texts = []
    total_len = 0

    for page in page_text["pages"]:
        page_len = len(page["content"].encode("utf8"))
        if page_len > TEXT_LIMIT:
            logger.error("Single page too long for entity extraction")
            return

        if total_len + page_len > TEXT_LIMIT:
            # if adding another page would put us over the limit,
            # send the current chunk of text to be analyzed
            _extract_entities_text(document, "".join(texts))
            texts = []
        else:
            # otherwise append the current page and accumulate the length
            texts.append(page["content"])
            total_len += page_len

    # analyze the remaining text
    _extract_entities_text(document, "".join(texts))
