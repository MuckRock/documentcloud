# Third Party
from rules import add_perm, always_allow, is_authenticated, predicate

# DocumentCloud
from documentcloud.core.rules import skip_if_not_obj
from documentcloud.documents.rules import documents


@predicate
@skip_if_not_obj
def can_change_document(user, section):
    return documents.can_change(user, section.document)


can_change = is_authenticated & can_change_document


add_perm("documents.view_section", always_allow)
add_perm("documents.add_section", is_authenticated)
add_perm("documents.change_section", can_change)
add_perm("documents.delete_section", can_change)
