# Third Party
from rules import add_perm, always_deny, is_authenticated, is_staff, predicate

# DocumentCloud
from documentcloud.core.rules import skip_if_not_obj

add_perm("addons.view_addon", is_staff)
add_perm("addons.add_addon", is_staff)
add_perm("addons.change_addon", is_staff)
add_perm("addons.delete_addon", is_staff)


@predicate
@skip_if_not_obj
def is_owner(user, run):
    return user == run.user


add_perm("addons.view_addonrun", is_owner)
add_perm("addons.add_addonrun", is_staff)
add_perm("addons.change_addonrun", is_authenticated & is_owner)
add_perm("addons.delete_addonrun", always_deny)
