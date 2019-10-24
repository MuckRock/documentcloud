# pylint: disable=unused-argument, invalid-unary-operand-type

# Third Party
from rules import add_perm, always_deny, is_authenticated, predicate

# DocumentCloud
from documentcloud.documents.rules import skip_if_not_obj
from documentcloud.organizations.models import Organization
from documentcloud.projects.models import Project


@predicate
@skip_if_not_obj
def is_organization(user, user_):
    # separate filters will do two joins in SQL
    return Organization.objects.filter(users=user).filter(users=user_).exists()


@predicate
@skip_if_not_obj
def is_collaborator(user, user_):
    # separate filters will do two joins in SQL
    return (
        Project.objects.filter(collaborators=user).filter(collaborators=user_).exists()
    )


@predicate
@skip_if_not_obj
def is_me(user, user_):
    return user == user_


can_view = is_authenticated & (is_organization | is_collaborator)

add_perm("users.view_user", can_view)
add_perm("users.add_user", always_deny)
add_perm("users.change_user", is_authenticated & is_me)
add_perm("users.delete_user", always_deny)
