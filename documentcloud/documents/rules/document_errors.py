# Third Party
from rules import add_perm, always_allow, always_deny

add_perm("documents.view_documenterror", always_allow)
add_perm("documents.add_documenterror", always_deny)
add_perm("documents.change_documenterror", always_deny)
add_perm("documents.delete_documenterror", always_deny)
