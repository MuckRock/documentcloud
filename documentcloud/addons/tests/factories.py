# Third Party
import factory


class AddOnFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f"Add-On {n}")

    user = factory.LazyAttribute(lambda obj: obj.github_account.user)
    organization = factory.LazyAttribute(lambda obj: obj.user.organization)

    repository = factory.Sequence(lambda n: f"owner/repo-{n}")

    github_account = factory.SubFactory(
        "documentcloud.addons.tests.factories.GitHubAccountFactory"
    )

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

    user = factory.SubFactory("documentcloud.users.tests.factories.UserFactory")

    class Meta:
        model = "addons.AddOnRun"


class GitHubAccountFactory(factory.django.DjangoModelFactory):

    user = factory.SubFactory("documentcloud.users.tests.factories.UserFactory")
    uid = factory.Sequence(lambda n: n)
    token = factory.Sequence(lambda n: f"ghu_{n}")

    class Meta:
        model = "addons.GitHubAccount"
