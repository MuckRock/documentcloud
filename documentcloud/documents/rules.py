# pylint: disable=unused-argument, invalid-unary-operand-type

# Third Party
from rules import add_perm, is_authenticated, predicate

# DocumentCloud
from documentcloud.documents.models import Access


@predicate
def is_owner(user, resource):
    return user == resource.user


@predicate
def is_organization(user, resource):
    return user.organization == resource.organization


def has_access(access):
    @predicate(f"has_access:{access}")
    def inner(user, resource):
        return resource.access == access

    return inner


# XXX projects

can_change = is_authenticated & (
    (~has_access(Access.invisible) & is_owner)
    | (has_access(Access.organization) & is_organization)
)
can_view = has_access(Access.public) | can_change
can_delete = can_change

add_perm("documents.view_document", can_view)
add_perm("documents.add_document", is_authenticated)
add_perm("documents.change_document", can_change)
add_perm("documents.delete_document", can_delete)

add_perm("documents.view_note", can_view)
add_perm("documents.add_note", is_authenticated)
add_perm("documents.change_note", can_change)
add_perm("documents.delete_note", can_delete)
