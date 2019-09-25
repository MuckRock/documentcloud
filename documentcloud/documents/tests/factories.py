# Third Party
import factory

# DocumentCloud
from documentcloud.core.choices import Language
from documentcloud.documents.choices import Access


class DocumentFactory(factory.django.DjangoModelFactory):
    title = factory.Sequence(lambda n: f"Document {n}")

    user = factory.SubFactory("documentcloud.users.tests.factories.UserFactory")
    organization = factory.LazyAttribute(lambda obj: obj.user.organization)
    access = Access.public
    language = Language.english

    class Meta:
        model = "documents.Document"


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
    top = 10
    left = 20
    bottom = 100
    right = 50

    class Meta:
        model = "documents.Note"


class SectionFactory(factory.django.DjangoModelFactory):
    document = factory.SubFactory(
        "documentcloud.documents.tests.factories.DocumentFactory"
    )
    page_number = factory.Sequence(lambda n: n)
    title = factory.Sequence(lambda n: f"Section #{n}")

    class Meta:
        model = "documents.Section"
