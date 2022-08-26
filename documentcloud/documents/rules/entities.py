# pylint: disable=unused-argument, invalid-unary-operand-type


# Third Party
from rules import add_perm, always_allow, is_authenticated, predicate

# DocumentCloud
from documentcloud.core.rules import skip_if_not_obj


add_perm("documents.view_entity", always_allow)
add_perm("documents.add_entity", is_authenticated)
