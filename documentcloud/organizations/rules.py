# pylint: disable=unused-argument, invalid-unary-operand-type

# Third Party
from rules import add_perm, always_deny, is_authenticated, predicate


@predicate
def is_member(user, organization):
    return organization.has_member(user)


add_perm("organizations.view_organization", is_authenticated & is_member)
add_perm("organizations.add_organization", always_deny)
add_perm("organizations.change_organization", always_deny)
add_perm("organizations.delete_organization", always_deny)
