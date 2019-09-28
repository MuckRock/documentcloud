# Django
from django.contrib.auth.models import AnonymousUser

# Third Party
import pytest

# DocumentCloud
from documentcloud.organizations.tests.factories import OrganizationFactory
from documentcloud.users.tests.factories import UserFactory


@pytest.mark.django_db()
def test_rules():
    anonymous = AnonymousUser()
    public_member = UserFactory()
    private_member = UserFactory()

    public_organization = OrganizationFactory(private=False, members=[public_member])
    private_organization = OrganizationFactory(private=True, members=[private_member])

    for user, organization, can_view in [
        (anonymous, public_organization, True),
        (public_member, public_organization, True),
        (private_member, public_organization, True),
        (anonymous, private_organization, False),
        (public_member, private_organization, False),
        (private_member, private_organization, True),
    ]:
        assert (
            user.has_perm("organizations.view_organization", organization) is can_view
        )
