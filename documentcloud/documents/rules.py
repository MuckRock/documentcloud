# pylint: disable=unused-argument, invalid-unary-operand-type

# Third Party
from rules import add_perm, is_authenticated, predicate

# DocumentCloud
from documentcloud.documents.models import Access


@predicate
def is_owner(user, document):
    return user == document.user


@predicate
def is_organization(user, document):
    return user.organization == document.organization


def has_access(access):
    @predicate(f"has_access:{access}")
    def inner(user, document):
        return document.access == access

    return inner


# XXX freelancers?
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
