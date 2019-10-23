# Django
from rest_framework import permissions

# DocumentCloud
from documentcloud.documents.models import Document


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
            and request.auth is not None
            and self.token_permissions.issubset(request.auth["permissions"])
        )


class DocumentTokenPermissions(TokenPermissions):
    """Allow the processing functions to update documents"""

    token_permissions = {"processing"}
    token_methods = ["PUT", "PATCH"]


class DocumentErrorTokenPermissions(TokenPermissions):
    """Alow the processing functions to create errors"""

    token_permissions = {"processing"}
    token_methods = ["POST"]
