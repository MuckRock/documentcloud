# pylint: disable=unused-argument, invalid-unary-operand-type

# Third Party
from rules import add_perm, always_allow, is_authenticated, predicate

# DocumentCloud
from documentcloud.documents.models import Access

# These predicates work for documents and notes


@predicate
def is_owner(user, resource):
    return user == resource.user


@predicate
def is_organization(user, resource):
    return user.organization == resource.organization


def has_access(*accesses):
    @predicate(f"has_access:{accesses}")
    def inner(user, resource):
        return resource.access in accesses

    return inner


# These predicates are for documents only


@predicate
def is_edit_collaborator(user, document):
    return document.projects.filter(
        collaborators=user, projectmembership__edit_access=True
    ).exists()


@predicate
def is_collaborator(user, document):
    return document.projects.filter(collaborators=user).exists()


can_change_document = is_authenticated & (
    (~has_access(Access.invisible) & (is_owner | is_edit_collaborator))
    | (has_access(Access.organization, Access.public) & is_organization)
)
can_view_document = (
    has_access(Access.public)
    | can_change_document
    | (~has_access(Access.invisible) & is_authenticated & is_collaborator)
)

add_perm("documents.view_document", can_view_document)
add_perm("documents.add_document", is_authenticated)
add_perm("documents.change_document", can_change_document)
add_perm("documents.delete_document", can_change_document)

can_change_note = is_authenticated & (
    (~has_access(Access.invisible) & is_owner)
    | (has_access(Access.organization, Access.public) & is_organization)
)
can_view_note = has_access(Access.public) | can_change_note

add_perm("documents.view_note", can_view_note)
add_perm("documents.add_note", is_authenticated)
add_perm("documents.change_note", can_change_note)
add_perm("documents.delete_note", can_change_note)


# These predicates are for sections only


@predicate
def can_change_section(user, section):
    return can_change_document(user, section.document)


add_perm("documents.view_section", always_allow)
add_perm("documents.add_section", is_authenticated)
add_perm("documents.change_section", can_change_section)
add_perm("documents.delete_section", can_change_section)
