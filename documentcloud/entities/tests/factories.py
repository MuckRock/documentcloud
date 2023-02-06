# Standard Library

# Standard Library
import datetime

# Third Party
import factory

# DocumentCloud
from documentcloud.entities.choices import EntityAccess


class EntityFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f"User {n}")
    localized_names = factory.Sequence(lambda n: {"en": "test {n}", "es": "prueba {n}"})
    wikidata_id = factory.Sequence(lambda n: "Q{n}")
    wikipedia_url = factory.Sequence(
        lambda n: {
            "en": "https://en.wikipedia.org/wiki/{n}",
            "es": "https://es.wikipedia.org/wiki/{n}",
        }
    )
    # Assuming entity is public for now.
    owner = None
    # owner = factory.SubFactory("documentcloud.users.tests.factories.UserFactory")
    description = factory.Sequence(
        lambda n: {"en": "{n} is good.", "es": "{n} es bueno."}
    )
    created_at = factory.LazyFunction(datetime.datetime.utcnow)
    updated_at = factory.LazyFunction(datetime.datetime.utcnow)
    access = EntityAccess.public
