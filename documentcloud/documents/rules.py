# pylint: disable=unused-argument, invalid-unary-operand-type

# Standard Library
from functools import wraps

# Third Party
from rules import add_perm, always_allow, always_deny, is_authenticated, predicate

# DocumentCloud
from documentcloud.documents.choices import Status
from documentcloud.documents.models import Access


def skip_if_not_obj(func):
    """Decorator for predicates
    Skip the predicate if obj is None"""

    @wraps(func)
    def inner(user, obj):
        if obj is None:
            return None
        else:
            return func(user, obj)

    return inner


# These predicates work for documents and notes


@predicate
@skip_if_not_obj
def is_owner(user, resource):
    return user == resource.user


@predicate
@skip_if_not_obj
def is_organization(user, resource):
    return resource.organization.has_member(user)


def has_access(*accesses):
    @predicate(f"has_access:{accesses}")
    @skip_if_not_obj
    def inner(user, resource):
        return resource.access in accesses

    return inner


def has_status(*statuses):
    @predicate(f"has_status:{statuses}")
    @skip_if_not_obj
    def inner(user, resource):
        return resource.status in statuses

    return inner


# These predicates are for documents only


@predicate
@skip_if_not_obj
def is_edit_collaborator(user, document):
    return document.projects.filter(
        collaborators=user, projectmembership__edit_access=True
    ).exists()


@predicate
@skip_if_not_obj
def is_collaborator(user, document):
    return document.projects.filter(collaborators=user).exists()


can_change_document = is_authenticated & (
    (~has_access(Access.invisible) & (is_owner | is_edit_collaborator))
    | (has_access(Access.organization, Access.public) & is_organization)
)
can_view_document = (
    (has_access(Access.public) & has_status(Status.success, Status.readable))
    | can_change_document
    | (~has_access(Access.invisible) & is_authenticated & is_collaborator)
)

add_perm("documents.view_document", can_view_document)
add_perm("documents.add_document", is_authenticated)
add_perm("documents.change_document", can_change_document)
add_perm("documents.delete_document", can_change_document)

# XXX refactor into separate files


@predicate
@skip_if_not_obj
def change_change_note_document(user, note):
    return can_change_document(user, note.document)


can_change_note = is_authenticated & (
    (~has_access(Access.invisible) & is_owner)
    | (has_access(Access.organization, Access.public) & change_change_note_document)
)
can_view_note = has_access(Access.public) | can_change_note

add_perm("documents.view_note", can_view_note)
add_perm("documents.add_note", is_authenticated)
add_perm("documents.change_note", can_change_note)
add_perm("documents.delete_note", can_change_note)


# These predicates are for sections only


@predicate
@skip_if_not_obj
def can_change_section(user, section):
    return can_change_document(user, section.document)


add_perm("documents.view_section", always_allow)
add_perm("documents.add_section", is_authenticated)
add_perm("documents.change_section", is_authenticated & can_change_section)
add_perm("documents.delete_section", is_authenticated & can_change_section)


add_perm("documents.view_documenterror", always_allow)
add_perm("documents.add_documenterror", always_deny)
add_perm("documents.change_documenterror", always_deny)
add_perm("documents.delete_documenterror", always_deny)
