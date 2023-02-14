# pylint: disable=unused-argument


# Third Party
from rules import add_perm, is_authenticated, predicate

# DocumentCloud
from documentcloud.core.rules import skip_if_not_obj
from documentcloud.entities.choices import EntityAccess


@predicate
@skip_if_not_obj
def is_owner(user, entity):
    return user == entity.user


def has_access(*accesses):
    @predicate(f"has_access:{accesses}")
    @skip_if_not_obj
    def inner(user, entity):
        return entity.access in accesses

    return inner


can_view = has_access(EntityAccess.public) | (is_authenticated & is_owner)
can_change = has_access(EntityAccess.private) & is_authenticated & is_owner

add_perm("entities.view_entity", can_view)
add_perm("entities.add_entity", is_authenticated)
add_perm("entities.change_entity", can_change)
add_perm("entities.delete_entity", can_change)
