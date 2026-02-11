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
    admin_collaborator = UserFactory()
    edit_collaborator = UserFactory()
    view_collaborator = UserFactory()

    public_project = ProjectFactory(
        admin_collaborators=[admin_collaborator],
        edit_collaborators=[edit_collaborator],
        collaborators=[view_collaborator],
        private=False,
    )
    private_project = ProjectFactory(
        admin_collaborators=[admin_collaborator],
        edit_collaborators=[edit_collaborator],
        collaborators=[view_collaborator],
        private=True,
    )

    for user, project, can_view, can_change in [
        (anonymous, public_project, True, False),
        (anonymous, private_project, False, False),
        (admin_collaborator, public_project, True, True),
        (admin_collaborator, private_project, True, True),
        (edit_collaborator, public_project, True, False),
        (edit_collaborator, private_project, True, False),
        (view_collaborator, public_project, True, False),
        (view_collaborator, private_project, True, False),
    ]:
        assert user.has_perm("projects.view_project", project) is can_view
        assert user.has_perm("projects.change_project_all", project) is can_change
        assert user.has_perm("projects.delete_project", project) is can_change
