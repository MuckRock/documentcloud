# Third Party
import factory


class PluginFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f"Plugin {n}")

    user = factory.SubFactory(
        "documentcloud.users.tests.factories.UserFactory", is_staff=True
    )
    organization = factory.LazyAttribute(lambda obj: obj.user.organization)

    repository = factory.Sequence(lambda n: f"owner/repo-{n}")
    github_token = factory.Sequence(lambda n: f"ghp_{n}")

    parameters = [{"name": "test", "type": "text", "label": "Test"}]

    class Meta:
        model = "plugins.Plugin"


class PluginRunFactory(factory.django.DjangoModelFactory):
    plugin = factory.SubFactory("documentcloud.plugins.tests.factories.PluginFactory")

    user = factory.SubFactory(
        "documentcloud.users.tests.factories.UserFactory", is_staff=True
    )

    class Meta:
        model = "plugins.PluginRun"
