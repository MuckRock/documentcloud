# pylint: disable=unused-argument

# Third Party
from rules import add_perm, always_deny, is_authenticated, predicate

# DocumentCloud
from documentcloud.core.rules import skip_if_not_obj
from documentcloud.documents.choices import Access
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


@predicate
@skip_if_not_obj
def has_public_document(user, user_):
    user_.documents.filter(access=Access.public).exists()


can_view = has_public_document | (
    is_authenticated & (is_organization | is_collaborator)
)
can_change = is_authenticated & is_me

add_perm("users.view_user", can_view)
add_perm("users.add_user", always_deny)
add_perm("users.change_user", can_change)
add_perm("users.delete_user", always_deny)
