# Third Party
from rules import add_perm, always_deny, is_staff, predicate

# DocumentCloud
from documentcloud.core.rules import skip_if_not_obj

add_perm("plugins.view_plugin", is_staff)
add_perm("plugins.add_plugin", is_staff)
add_perm("plugins.change_plugin", is_staff)
add_perm("plugins.delete_plugin", is_staff)


@predicate
@skip_if_not_obj
def is_owner(user, run):
    return user == run.user


add_perm("plugins.view_pluginrun", is_owner)
add_perm("plugins.add_pluginrun", is_staff)
add_perm("plugins.change_pluginrun", is_owner)
add_perm("plugins.delete_pluginrun", always_deny)
