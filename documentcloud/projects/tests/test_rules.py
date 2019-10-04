# Django
from django.contrib.auth.models import AnonymousUser

# Third Party
import pytest

# DocumentCloud
from documentcloud.projects.tests.factories import ProjectFactory
from documentcloud.users.tests.factories import UserFactory


@pytest.mark.django_db()
def test_project_rules():
    anonymous = AnonymousUser()
    user = UserFactory()
    collaborator = UserFactory()

    public_project = ProjectFactory(collaborators=[collaborator], private=False)
    private_project = ProjectFactory(collaborators=[collaborator], private=True)

    for user, project, can_view, can_change in [
        (anonymous, public_project, True, False),
        (anonymous, private_project, False, False),
        (user, public_project, True, False),
        (user, private_project, False, False),
        (collaborator, public_project, True, True),
        (collaborator, private_project, True, True),
    ]:
        assert user.has_perm("projects.view_project", project) is can_view
        assert user.has_perm("projects.change_project", project) is can_change
        assert user.has_perm("projects.delete_project", project) is can_change
