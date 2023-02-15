# Standard Library

import datetime

# Third Party
import factory

# DocumentCloud
from documentcloud.entities.choices import EntityAccess


class EntityFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f"User {n}")
    localized_names = factory.Sequence(
        lambda n: {"en": f"test {n}", "es": f"prueba {n}"}
    )
    wikidata_id = factory.Sequence(lambda n: f"Q{n}")
    wikipedia_url = factory.Sequence(
        lambda n: {
            "en": f"https://en.wikipedia.org/wiki/{n}",
            "es": f"https://es.wikipedia.org/wiki/{n}",
        }
    )
    # Assuming entity is public for now.
    user = None
    description = factory.Sequence(
        lambda n: {"en": f"{n} is good.", "es": f"{n} es bueno."}
    )
    access = EntityAccess.public

    class Meta:
        model = "entities.Entity"


class PrivateEntityFactory(EntityFactory):
    user = factory.SubFactory("documentcloud.users.tests.factories.UserFactory")
    wikidata_id = None

    class Meta:
        model = "entities.Entity"


class EntityOccurrenceFactory(factory.django.DjangoModelFactory):
    document = factory.SubFactory(
        "documentcloud.documents.tests.factories.DocumentFactory"
    )
    entity = factory.SubFactory("documentcloud.entities.tests.factories.EntityFactory")

    class Meta:
        model = "entities.EntityOccurrence"
