# pylint: disable=unused-argument, invalid-unary-operand-type

# Third Party
from rules import add_perm, always_deny, is_authenticated, predicate

# These predicates are for projects


@predicate
def is_private(user, project):
    return project.private


@predicate
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
def can_view_project(user, resource):
    return can_view(user, resource.project)


@predicate
def can_change_project(user, resource):
    return can_change(user, resource.project)


add_perm("projects.view_projectmembership", can_view_project)
add_perm("projects.add_projectmembership", can_change_project)
add_perm("projects.change_projectmembership", can_change_project)
add_perm("projects.delete_projectmembership", can_change_project)

add_perm("projects.view_collaboration", can_change_project)
add_perm("projects.add_collaboration", can_change_project)
add_perm("projects.change_collaboration", always_deny)
add_perm("projects.delete_collaboration", can_change_project)
