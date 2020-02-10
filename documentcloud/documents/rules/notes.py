# pylint: disable=unused-argument, invalid-unary-operand-type


# Third Party
from rules import add_perm, is_authenticated, predicate

# DocumentCloud
from documentcloud.core.rules import skip_if_not_obj
from documentcloud.documents.models import Access
from documentcloud.documents.rules import documents


@predicate
@skip_if_not_obj
def is_owner(user, note):
    return user == note.user


@predicate
@skip_if_not_obj
def is_organization(user, note):
    return note.organization.has_member(user)


def has_access(*accesses):
    @predicate(f"has_access:{accesses}")
    @skip_if_not_obj
    def inner(user, note):
        return note.access in accesses

    return inner


def has_status(*statuses):
    @predicate(f"has_status:{statuses}")
    @skip_if_not_obj
    def inner(user, note):
        return note.status in statuses

    return inner


@predicate
@skip_if_not_obj
def change_change_document(user, note):
    return documents.can_change(user, note.document)


can_change = is_authenticated & (
    (~has_access(Access.invisible) & is_owner)
    | (has_access(Access.organization, Access.public) & change_change_document)
)
can_view = has_access(Access.public) | can_change

add_perm("documents.view_note", can_view)
add_perm("documents.add_note", is_authenticated)
add_perm("documents.change_note", can_change)
add_perm("documents.delete_note", can_change)
