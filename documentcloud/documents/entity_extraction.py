# Third Party
from google.cloud import language_v1
from google.cloud.language_v1.types.language_service import AnalyzeEntitiesResponse

# DocumentCloud
from documentcloud.documents.models import Entity, EntityOccurence


def extract_entities(document):
    """Extract the entities from a document"""
    # XXX ensure no entities yet? or clear existing?
    client = language_v1.LanguageServiceClient()
    text = document.get_text()
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
