# Django
from rest_framework import permissions


class Permissions(permissions.DjangoObjectPermissions):
    """Use Django Object permissions as the base for our Document permissions"""

    def has_permission(self, request, view):
        """Authenticated users permissions will be checked on a per object basis
        Return true here to continue to the object check
        Anonymous users have read-only access
        """
        if request.user.is_authenticated:
            return True
        else:
            return request.method in permissions.SAFE_METHODS
