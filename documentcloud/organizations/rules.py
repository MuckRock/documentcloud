# pylint: disable=unused-argument, invalid-unary-operand-type

# Third Party
from rules import add_perm, always_deny, is_authenticated, predicate

# DocumentCloud
from documentcloud.documents.rules import skip_if_not_obj


@predicate
@skip_if_not_obj
def is_private(user, organization):
    return organization.private


@predicate
@skip_if_not_obj
def is_member(user, organization):
    return organization.has_member(user)


is_public = ~is_private

add_perm("organizations.view_organization", is_public | (is_authenticated & is_member))
add_perm("organizations.add_organization", always_deny)
add_perm("organizations.change_organization", always_deny)
add_perm("organizations.delete_organization", always_deny)
