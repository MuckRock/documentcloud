# Third Party
from rules import add_perm, always_deny, is_staff

add_perm("statistics.view_statistics", is_staff)
add_perm("statistics.add_statistics", always_deny)
add_perm("statistics.change_statistics", always_deny)
add_perm("statistics.delete_statistics", always_deny)
