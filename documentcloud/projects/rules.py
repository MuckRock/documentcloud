# pylint: disable=unused-argument, invalid-unary-operand-type

# Third Party
from rules import add_perm, always_deny, is_authenticated, predicate

# DocumentCloud
from documentcloud.documents.rules import skip_if_not_obj

# These predicates are for projects


@predicate
@skip_if_not_obj
def is_private(user, project):
    return project.private


@predicate
@skip_if_not_obj
def is_collaborator(user, project):
    return project.collaborators.filter(pk=user.pk).exists()


is_public = ~is_private

can_view = is_public | (is_authenticated & is_collaborator)

can_change = is_authenticated & is_collaborator

add_perm("projects.view_project", can_view)
add_perm("projects.add_project", is_authenticated)
add_perm("projects.change_project", can_change)
add_perm("projects.delete_project", can_change)


# These predicates are for project memberships and collaborators


@predicate
@skip_if_not_obj
def can_view_project(user, resource):
    return can_view(user, resource.project)


@predicate
@skip_if_not_obj
def can_change_project(user, resource):
    return can_change(user, resource.project)


add_perm("projects.view_projectmembership", can_view_project)
add_perm("projects.add_projectmembership", is_authenticated)
add_perm("projects.change_projectmembership", is_authenticated & can_change_project)
add_perm("projects.delete_projectmembership", is_authenticated & can_change_project)

add_perm("projects.view_collaboration", can_view_project)
add_perm("projects.add_collaboration", is_authenticated)
add_perm("projects.change_collaboration", always_deny)
add_perm("projects.delete_collaboration", is_authenticated & can_change_project)
