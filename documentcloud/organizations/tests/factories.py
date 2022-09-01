# Django
from django.utils.text import slugify

# Third Party
import factory
from squarelet_auth.organizations.models import Membership


class OrganizationFactory(factory.django.DjangoModelFactory):
    """A factory for creating Organization test objects."""

    name = factory.Sequence(lambda n: f"Organization {n}")
    slug = factory.LazyAttribute(lambda obj: slugify(obj.name))
    individual = False
    entitlement = factory.SubFactory(
        "documentcloud.organizations.tests.factories.FreeEntitlementFactory"
    )

    class Meta:
        model = "organizations.Organization"
        django_get_or_create = ("slug",)

    @factory.post_generation
    def members(self, create, extracted, **kwargs):
        if create and extracted:
            for user in extracted:
                Membership.objects.create(user=user, organization=self)


class MembershipFactory(factory.django.DjangoModelFactory):
    """A factory for creating Membership test objects."""

    class Meta:
        model = "squarelet_auth_organizations.Membership"
        django_get_or_create = ("user", "organization")

    user = factory.SubFactory("documentcloud.users.tests.factories.UserFactory")
    organization = factory.SubFactory(
        "documentcloud.organizations.tests.factories.OrganizationFactory"
    )
    active = True


class EntitlementFactory(factory.django.DjangoModelFactory):
    """A factory for creating Entitlement test objects"""

    class Meta:
        model = "squarelet_auth_organizations.Entitlement"
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Entitlement {n}")
    slug = factory.LazyAttribute(lambda obj: slugify(obj.name))
    resources = {
        "minimum_users": 1,
        "base_pages": 0,
        "pages_per_user": 0,
        "feature_level": 0,
    }


class FreeEntitlementFactory(EntitlementFactory):
    """A free entitlement factory"""

    name = "Free"


class ProfessionalEntitlementFactory(EntitlementFactory):
    """A professional entitlement factory"""

    name = "Professional"
    resources = {
        "minimum_users": 1,
        "base_pages": 200,
        "pages_per_user": 0,
        "feature_level": 1,
    }


class OrganizationEntitlementFactory(EntitlementFactory):
    """An organization entitlement factory"""

    name = "Organization"
    resources = {
        "minimum_users": 5,
        "base_pages": 500,
        "pages_per_user": 50,
        "feature_level": 2,
    }
