# pylint: disable=unused-argument, invalid-unary-operand-type


# Third Party
from rules import add_perm, is_authenticated, predicate

# DocumentCloud
from documentcloud.core.rules import skip_if_not_obj
from documentcloud.documents.choices import Status
from documentcloud.documents.models import Access


@predicate
@skip_if_not_obj
def is_owner(user, document):
    return user == document.user


@predicate
@skip_if_not_obj
def is_organization(user, document):
    return document.organization.has_member(user)


def has_access(*accesses):
    @predicate(f"has_access:{accesses}")
    @skip_if_not_obj
    def inner(user, document):
        return document.access in accesses

    return inner


def has_status(*statuses):
    @predicate(f"has_status:{statuses}")
    @skip_if_not_obj
    def inner(user, document):
        return document.status in statuses

    return inner


@predicate
@skip_if_not_obj
def is_edit_collaborator(user, document):
    return document.projects.filter(
        collaborators=user, projectmembership__edit_access=True
    ).exists()


@predicate
@skip_if_not_obj
def is_collaborator(user, document):
    return document.projects.filter(collaborators=user).exists()


can_change = is_authenticated & (
    (~has_access(Access.invisible) & (is_owner | is_edit_collaborator))
    | (has_access(Access.organization, Access.public) & is_organization)
)
can_view = (
    (has_access(Access.public) & has_status(Status.success, Status.readable))
    | can_change
    | (~has_access(Access.invisible) & is_authenticated & is_collaborator)
)

add_perm("documents.view_document", can_view)
add_perm("documents.add_document", is_authenticated)
add_perm("documents.change_document", can_change)
add_perm("documents.delete_document", can_change)
