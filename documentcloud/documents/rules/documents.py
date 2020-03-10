# pylint: disable=unused-argument, invalid-unary-operand-type


# Third Party
from rules import add_perm, is_authenticated, predicate

# DocumentCloud
from documentcloud.core.rules import skip_if_not_obj
from documentcloud.documents.choices import Status
from documentcloud.documents.models import Access
from documentcloud.projects.choices import CollaboratorAccess


@predicate
@skip_if_not_obj
def is_owner(user, document):
    return user == document.user


@predicate
@skip_if_not_obj
def is_organization(user, document):
    return document.organization.has_member(user)


def has_access(*accesses):
    @predicate(f"has_access:{accesses}")
    @skip_if_not_obj
    def inner(user, document):
        return document.access in accesses

    return inner


def has_status(*statuses):
    @predicate(f"has_status:{statuses}")
    @skip_if_not_obj
    def inner(user, document):
        return document.status in statuses

    return inner


@predicate
@skip_if_not_obj
def is_edit_collaborator(user, document):
    return document.projects.filter(
        collaborators=user,
        projectmembership__edit_access=True,
        collaboration__access__in=(CollaboratorAccess.admin, CollaboratorAccess.edit),
    ).exists()


@predicate
@skip_if_not_obj
def is_view_collaborator(user, document):
    # the document must be in the project with edit access in order for it
    # to be shared for viewing with view collaborators
    return document.projects.filter(
        collaborators=user, projectmembership__edit_access=True
    ).exists()


# nobody can see invisible or deleted documents
default_limit = (
    is_authenticated & ~has_access(Access.invisible) & ~has_status(Status.deleted)
)

# share access is for adding a document to a project with edit access
# it is stricter than edit access to allow people to revoke edit access
# through a project without the possibility of you propagating the edit
# access through your own projects
# you must be logged in to have share access
# nobody has any access to invisible documents
can_share = default_limit & (
    # you have share access if you are the owner and the document is not public
    # public documents restrict access to the organization to prevent
    # abuse to embedded documents
    (is_owner & ~has_access(Access.public))
    # you also can have access if you are in the same organization
    # and the access is organization or public
    | (has_access(Access.organization, Access.public) & is_organization)
)
# you can edit the document if you can share it, or additionally
# if it was shared with you for editing and it is not public
can_change = can_share | (
    default_limit & is_edit_collaborator & ~has_access(Access.public)
)
# you can view a document if you can change it or if it is public
# being a non-edit collaborator does not give you view permissions
# so that an owner may revoke share permissions through projects
can_view = (
    # public documents which have succesfully processed or in readable state
    # can be viewed by everyone
    (has_access(Access.public) & has_status(Status.success, Status.readable))
    # documents shared with you for viewing through a project
    | default_limit & is_view_collaborator
    # if you have edit access you also have view access
    | can_change
)

add_perm("documents.view_document", can_view)
add_perm("documents.add_document", is_authenticated)
add_perm("documents.change_document", can_change)
add_perm("documents.share_document", can_share)
add_perm("documents.delete_document", can_share)
