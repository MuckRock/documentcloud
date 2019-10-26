# Django
from rest_framework import permissions


class DjangoObjectPermissionsOrAnonReadOnly(permissions.DjangoObjectPermissions):
    """Use Django Object permissions as the base for our permissions
    Allow anonymous read-only access
    """

    authenticated_users_only = False


class TokenPermissions(permissions.BasePermission):
    """For views which allow authorization via special token"""

    token_permissions = frozenset()
    token_methods = permissions.SAFE_METHODS

    def has_permission(self, request, view):
        """
        Allow token authed requests with correct method and permissions
        """
        return (
            request.method in self.token_methods
            and hasattr(request, "auth")
        if request.user.is_authenticated:
            return True
        elif (
            hasattr(request, "auth")
            and request.auth is not None
            and request.method in ["PUT", "PATCH"]
        ):
            # If there is an auth token, allow it for PUT and PATCH requests
            return True
        else:
            return request.method in permissions.SAFE_METHODS

    def has_object_permission(self, request, view, obj):
        """Check for processing token"""

        # A processing token allows for updating documents
        valid_token = (
            hasattr(request, "auth")
            and request.auth is not None
            and self.token_permissions.issubset(request.auth["permissions"])
        )
        if (
            valid_token
            and request.method in ["PUT", "PATCH"]
            and isinstance(obj, Document)
        ):
            return True
        else:
            return super().has_object_permission(request, view, obj)



class DocumentTokenPermissions(TokenPermissions):
    """Allow the processing functions to update documents"""

    token_permissions = {"processing"}
    token_methods = ["PUT", "PATCH"]


class DocumentErrorTokenPermissions(TokenPermissions):
    """Alow the processing functions to create errors"""

    token_permissions = {"processing"}
    token_methods = ["POST"]
