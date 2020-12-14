# Standard Library
from random import random

# Third Party
import factory

# DocumentCloud
from documentcloud.core.choices import Language
from documentcloud.documents.choices import Access, Status


class DocumentFactory(factory.django.DjangoModelFactory):
    title = factory.Sequence(lambda n: f"Document {n}")

    user = factory.SubFactory("documentcloud.users.tests.factories.UserFactory")
    organization = factory.LazyAttribute(lambda obj: obj.user.organization)
    access = Access.public
    language = Language.english
    status = Status.success

    class Meta:
        model = "documents.Document"


class DocumentErrorFactory(factory.django.DjangoModelFactory):
    document = factory.SubFactory(
        "documentcloud.documents.tests.factories.DocumentFactory"
    )
    message = factory.Faker("text")

    class Meta:
        model = "documents.DocumentError"


class PageFactory(factory.django.DjangoModelFactory):
    document = factory.SubFactory(
        "documentcloud.documents.tests.factories.DocumentFactory"
    )
    page_number = factory.Sequence(lambda n: n)
    text = factory.Faker("text")

    class Meta:
        model = "documents.Page"


class NoteFactory(factory.django.DjangoModelFactory):
    document = factory.SubFactory(
        "documentcloud.documents.tests.factories.DocumentFactory"
    )
    user = factory.LazyAttribute(lambda obj: obj.document.user)
    organization = factory.LazyAttribute(lambda obj: obj.document.user.organization)
    page_number = factory.Sequence(lambda n: n)
    title = factory.Sequence(lambda n: f"Note #{n}")
    content = factory.Faker("text")
    access = Access.public
    x1 = 0.1
    x2 = 0.2
    y1 = 0.3
    y2 = 0.4

    class Meta:
        model = "documents.Note"


class SectionFactory(factory.django.DjangoModelFactory):
    document = factory.SubFactory(
        "documentcloud.documents.tests.factories.DocumentFactory", page_count=100
    )
    page_number = factory.Iterator(range(100))
    title = factory.Sequence(lambda n: f"Section #{n}")

    class Meta:
        model = "documents.Section"


class LegacyEntityFactory(factory.django.DjangoModelFactory):
    document = factory.SubFactory(
        "documentcloud.documents.tests.factories.DocumentFactory"
    )
    kind = factory.Iterator(
        [
            "person",
            "organization",
            "place",
            "term",
            "email",
            "phone",
            "city",
            "state",
            "country",
        ]
    )
    value = factory.Sequence(lambda n: f"Value {n}")
    relevance = factory.LazyFunction(random)

    class Meta:
        model = "documents.LegacyEntity"


class EntityDateFactory(factory.django.DjangoModelFactory):
    document = factory.SubFactory(
        "documentcloud.documents.tests.factories.DocumentFactory"
    )
    date = factory.Faker("date")

    class Meta:
        model = "documents.EntityDate"
