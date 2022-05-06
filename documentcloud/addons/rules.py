# Third Party
from rules import add_perm, always_deny, is_authenticated, predicate

# DocumentCloud
from documentcloud.core.rules import skip_if_not_obj
from documentcloud.documents.models import Access
from documentcloud.documents.rules.documents import (
    has_access,
    is_organization,
    is_owner,
)

# pylint: disable=invalid-unary-operand-type


@predicate
@skip_if_not_obj
def is_removed(_user, add_on):
    return add_on.removed


can_view = (
    # everyone can view public add-ons
    has_access(Access.public)
    # the owner may view all of their add-ons
    | is_owner
    # add-ons shared among the organization may be viewed by those
    # in the organization
    | (has_access(Access.organization) & is_organization)
) & ~is_removed


add_perm("addons.view_addon", can_view)
add_perm("addons.add_addon", always_deny)
add_perm("addons.change_addon", is_authenticated & ~is_removed)
add_perm("addons.delete_addon", always_deny)


add_perm("addons.view_addonrun", is_authenticated & is_owner)
add_perm("addons.add_addonrun", is_authenticated)
add_perm("addons.change_addonrun", is_authenticated & is_owner)
add_perm("addons.delete_addonrun", always_deny)


add_perm("addons.view_addonevent", is_authenticated & is_owner)
add_perm("addons.add_addonevent", is_authenticated)
add_perm("addons.change_addonevent", is_authenticated & is_owner)
add_perm("addons.delete_addonevent", always_deny)
