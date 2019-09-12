# Standard Library
from uuid import uuid4

# Third Party
import factory


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "users.User"

    name = factory.Faker("name")
    email = factory.Faker("email")
    username = factory.Sequence(lambda n: "user_%d" % n)
    membership = factory.RelatedFactory(
        "documentcloud.organizations.tests.factories.MembershipFactory",
        "user",
        organization__individual=True,
        organization__uuid=factory.SelfAttribute("..user.uuid"),
    )

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        """Sets password"""
        # pylint: disable=unused-argument
        if extracted:
            self.set_password(extracted)
            if create:
                self.save()
