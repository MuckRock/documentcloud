# Django
from django.utils.text import slugify

# Third Party
import factory

# DocumentCloud
from documentcloud.organizations.models import Membership


class OrganizationFactory(factory.django.DjangoModelFactory):
    """A factory for creating Organization test objects."""

    name = factory.Sequence(lambda n: f"Organization {n}")
    slug = factory.LazyAttribute(lambda obj: slugify(obj.name))
    individual = False
    plan = factory.SubFactory(
        "documentcloud.organizations.tests.factories.FreePlanFactory"
    )

    class Meta:
        model = "organizations.Organization"

    @factory.post_generation
    def members(self, create, extracted, **kwargs):
        # pylint: disable=unused-argument
        if create and extracted:
            for user in extracted:
                Membership.objects.create(user=user, organization=self)


class MembershipFactory(factory.django.DjangoModelFactory):
    """A factory for creating Membership test objects."""

    class Meta:
        model = "organizations.Membership"

    user = factory.SubFactory("documentcloud.users.tests.factories.UserFactory")
    organization = factory.SubFactory(
        "documentcloud.organizations.tests.factories.OrganizationFactory"
    )
    active = True


class PlanFactory(factory.django.DjangoModelFactory):
    """A factory for creating Plan test objects"""

    class Meta:
        model = "organizations.Plan"
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: "Plan %d" % n)
    slug = factory.LazyAttribute(lambda obj: slugify(obj.name))


class FreePlanFactory(PlanFactory):
    """A free plan factory"""

    name = "Free"


class ProfessionalPlanFactory(PlanFactory):
    """A professional plan factory"""

    name = "Professional"
    minimum_users = 1
    base_pages = 200
    feature_level = 1


class OrganizationPlanFactory(PlanFactory):
    """An organization plan factory"""

    name = "Organization"
    minimum_users = 5
    base_pages = 500
    pages_per_user = 50
    feature_level = 2
