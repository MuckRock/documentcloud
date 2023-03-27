"""Permissions for entities"""

# pylint: disable=unused-argument


# Third Party
from rules import add_perm, is_authenticated, predicate

# DocumentCloud
from documentcloud.core.rules import skip_if_not_obj
from documentcloud.documents.rules import documents
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


@predicate
@skip_if_not_obj
def can_view_entity(user, entity_occurrence):
    return can_view(user, entity_occurrence.entity)


@predicate
@skip_if_not_obj
def can_view_document(user, entity_occurrence):
    return documents.can_view(user, entity_occurrence.document)


@predicate
@skip_if_not_obj
def can_change_document(user, entity_occurrence):
    return documents.can_change(user, entity_occurrence.document)


can_change_occurrence = is_authenticated & can_change_document & can_view_entity

add_perm("entities.view_entityoccurrence", can_view_document & can_view_entity)
add_perm("entities.add_entityoccurrence", is_authenticated)
add_perm("entities.change_entityoccurrence", can_change_occurrence)
add_perm("entities.delete_entityoccurrence", can_change_occurrence)
