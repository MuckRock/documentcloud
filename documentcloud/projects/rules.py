# pylint: disable=unused-argument, invalid-unary-operand-type

# Third Party
from rules import add_perm, is_authenticated, predicate

# DocumentCloud
from documentcloud.core.rules import skip_if_not_obj
from documentcloud.documents.rules import documents
from documentcloud.projects.choices import CollaboratorAccess

# These predicates are for projects


@predicate
@skip_if_not_obj
def is_private(user, project):
    return project.private


@predicate
@skip_if_not_obj
def is_collaborator(user, project):
    return project.collaborators.filter(pk=user.pk).exists()


@predicate
@skip_if_not_obj
def is_edit_collaborator(user, project):
    return project.collaborators.filter(
        pk=user.pk,
        collaboration__access__in=(CollaboratorAccess.admin, CollaboratorAccess.edit),
    ).exists()


@predicate
@skip_if_not_obj
def is_admin(user, project):
    return project.collaborators.filter(
        pk=user.pk, collaboration__access=CollaboratorAccess.admin
    ).exists()


is_public = ~is_private

can_view = is_public | (is_authenticated & is_collaborator)

can_change = is_authenticated & is_admin

can_add_remove = is_authenticated & is_edit_collaborator

add_perm("projects.view_project", can_view)
add_perm("projects.add_project", is_authenticated)
add_perm("projects.change_project", can_change)
add_perm("projects.add_remove_project", can_add_remove)
add_perm("projects.delete_project", can_change)


# These predicates are for project memberships and collaborators


@predicate
@skip_if_not_obj
def can_view_project(user, resource):
    return can_view(user, resource.project)


@predicate
@skip_if_not_obj
def can_view_document(user, project_membership):
    return documents.can_view(user, project_membership.document)


@predicate
@skip_if_not_obj
def can_change_project(user, resource):
    return can_change(user, resource.project)


@predicate
@skip_if_not_obj
def can_add_remove_project(user, resource):
    return can_add_remove(user, resource.project)


add_perm(
    "projects.view_projectmembership",
    is_authenticated & can_view_project & can_view_document,
)
add_perm("projects.add_projectmembership", is_authenticated)
add_perm(
    "projects.change_projectmembership",
    is_authenticated & can_add_remove_project & can_view_document,
)
add_perm(
    "projects.delete_projectmembership",
    is_authenticated & can_add_remove_project & can_view_document,
)

add_perm("projects.view_collaboration", is_authenticated & can_change_project)
add_perm("projects.add_collaboration", is_authenticated)
add_perm("projects.change_collaboration", is_authenticated & can_change_project)
add_perm("projects.delete_collaboration", is_authenticated & can_change_project)
