# pylint: disable=unused-argument, invalid-unary-operand-type


# Third Party
from rules import add_perm, always_allow, always_deny, is_authenticated

# DocumentCloud
from documentcloud.core.rules import skip_if_not_obj

add_perm("documents.view_entityoccurrence", always_allow)
add_perm("documents.add_entityoccurrence", is_authenticated)
add_perm("documents.change_entityoccurrence", always_deny)
add_perm("documents.delete_entityoccurrence", is_authenticated)
add_perm("documents.view_entity", always_allow)
add_perm("documents.add_entity", is_authenticated)
