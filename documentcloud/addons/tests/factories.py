# Third Party
import factory


class AddOnFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f"Add-On {n}")

    user = factory.SubFactory(
        "documentcloud.users.tests.factories.UserFactory", is_staff=True
    )
    organization = factory.LazyAttribute(lambda obj: obj.user.organization)

    repository = factory.Sequence(lambda n: f"owner/repo-{n}")
    github_token = factory.Sequence(lambda n: f"ghp_{n}")

    parameters = {
        "type": "object",
        "title": "Hello World",
        "required": ["name"],
        "properties": {"name": {"type": "string", "title": "Name"}},
    }

    class Meta:
        model = "addons.AddOn"


class AddOnRunFactory(factory.django.DjangoModelFactory):
    addon = factory.SubFactory("documentcloud.addons.tests.factories.AddOnFactory")

    user = factory.SubFactory(
        "documentcloud.users.tests.factories.UserFactory", is_staff=True
    )

    class Meta:
        model = "addons.AddOnRun"
