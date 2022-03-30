# Third Party
from rules import add_perm, always_deny, is_authenticated, is_staff

# DocumentCloud
from documentcloud.documents.models import Access
from documentcloud.documents.rules.documents import (
    has_access,
    is_organization,
    is_owner,
)

can_view = (
    # everyone can view public add-ons
    has_access(Access.public)
    # the owner may view all of their add-ons
    | is_owner
    # add-ons shared among the organization may be viewed by those
    # in the organization
    | (has_access(Access.organization) & is_organization)
)


add_perm("addons.view_addon", can_view)
add_perm("addons.add_addon", always_deny)
add_perm("addons.change_addon", is_authenticated & is_owner)
add_perm("addons.delete_addon", is_authenticated & is_owner)


add_perm("addons.view_addonrun", is_authenticated & is_owner)
add_perm("addons.add_addonrun", is_authenticated)
add_perm("addons.change_addonrun", is_authenticated & is_owner)
add_perm("addons.delete_addonrun", always_deny)
