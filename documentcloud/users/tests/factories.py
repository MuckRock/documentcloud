# Third Party
import factory
from squarelet_auth.organizations.models import Membership


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "users.User"
        django_get_or_create = ("username",)

    name = factory.Faker("name")
    email = factory.Faker("email")
    username = factory.Sequence(lambda n: f"user_{n}")
    membership = factory.RelatedFactory(
        "documentcloud.organizations.tests.factories.MembershipFactory",
        "user",
        organization__individual=True,
        organization__uuid=factory.SelfAttribute("..user.uuid"),
        organization__verified_journalist=True,
    )

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        """Sets password"""
        # pylint: disable=unused-argument
        if extracted:
            self.set_password(extracted)
            if create:
                self.save()

    @factory.post_generation
    def organizations(self, create, extracted, **kwargs):
        # pylint: disable=unused-argument
        if create and extracted:
            for organization in extracted:
                Membership.objects.create(user=self, organization=organization)
