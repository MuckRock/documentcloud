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
