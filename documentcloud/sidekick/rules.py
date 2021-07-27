# pylint: disable=unused-argument, invalid-unary-operand-type

# Third Party
from rules import add_perm, is_authenticated, predicate

# DocumentCloud
from documentcloud.core.rules import skip_if_not_obj
from documentcloud.projects import rules as projects_rules


@predicate
@skip_if_not_obj
def can_view(user, sidekick):
    return projects_rules.can_view(user, sidekick.project)


@predicate
@skip_if_not_obj
def can_change(user, sidekick):
    return projects_rules.can_change(user, sidekick.project)


add_perm("sidekick.view_sidekick", can_view)
add_perm("sidekick.add_sidekick", is_authenticated)
add_perm("sidekick.change_sidekick", is_authenticated & can_change)
add_perm("sidekick.delete_sidekick", is_authenticated & can_change)
