# Third Party
from rules import add_perm, is_staff

add_perm("plugins.view_plugin", is_staff)
add_perm("plugins.add_plugin", is_staff)
add_perm("plugins.change_plugin", is_staff)
add_perm("plugins.delete_plugin", is_staff)
