# Third Party
from rules import add_perm, always_allow, always_deny, is_authenticated

add_perm("documents.view_entityoccurence", always_allow)
add_perm("documents.add_entityoccurence", is_authenticated)
add_perm("documents.change_entityoccurence", always_deny)
add_perm("documents.delete_entityoccurence", always_deny)
