# Django
from django.contrib.auth.models import AnonymousUser

# Third Party
import pytest

# DocumentCloud
from documentcloud.organizations.tests.factories import OrganizationFactory
from documentcloud.projects.tests.factories import ProjectFactory
from documentcloud.users.tests.factories import UserFactory


@pytest.mark.django_db()
def test_rules():
    anonymous = AnonymousUser()
    myself = UserFactory()
    organization_user = UserFactory()
    collaborator = UserFactory()
    unknown_user = UserFactory()

    OrganizationFactory(members=[myself, organization_user])
    ProjectFactory(collaborators=[myself, collaborator])

    for user, user_, can_view, can_change in [
        (anonymous, organization_user, False, False),
        (myself, myself, True, True),
        (myself, organization_user, True, False),
        (myself, collaborator, True, False),
        (myself, unknown_user, False, False),
    ]:
        assert user.has_perm("users.view_user", user_) is can_view
        assert user.has_perm("users.change_user", user_) is can_change
