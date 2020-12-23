# Third Party
from rules import add_perm, always_allow, always_deny, is_authenticated

add_perm("documents.view_entityoccurrence", always_allow)
add_perm("documents.add_entityoccurrence", is_authenticated)
add_perm("documents.change_entityoccurrence", always_deny)
add_perm("documents.delete_entityoccurrence", always_deny)
