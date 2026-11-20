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
    non_collaborator = UserFactory()

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

    for user, project, can_view, can_change, can_view_collaborators in [
        (anonymous, public_project, True, False, False),
        (anonymous, private_project, False, False, False),
        (admin_collaborator, public_project, True, True, True),
        (admin_collaborator, private_project, True, True, True),
        (edit_collaborator, public_project, True, False, True),
        (edit_collaborator, private_project, True, False, True),
        (view_collaborator, public_project, True, False, True),
        (view_collaborator, private_project, True, False, True),
        (non_collaborator, public_project, True, False, False),
        (non_collaborator, private_project, False, False, False),
    ]:
        assert user.has_perm("projects.view_project", project) is can_view
        assert user.has_perm("projects.change_project_all", project) is can_change
        assert user.has_perm("projects.delete_project", project) is can_change
        assert (
            user.has_perm("projects.view_collaborators", project)
            is can_view_collaborators
        )
