# pylint: disable=unused-argument, invalid-unary-operand-type

# Third Party
from rules import add_perm, always_deny, is_authenticated, predicate


@predicate
def is_organization(user, user_):
    return user.organization.has_member(user_)


@predicate
def is_me(user, user_):
    return user == user_


add_perm("users.view_user", is_authenticated & is_organization)
add_perm("users.add_user", always_deny)
add_perm("users.change_user", is_authenticated & is_me)
add_perm("users.delete_user", always_deny)
