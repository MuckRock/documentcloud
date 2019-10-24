# Django
from rest_framework import permissions


class Permissions(permissions.DjangoObjectPermissions):
    """Use Django Object permissions as the base for our permissions
    Allow anonymous read-only access
    """

    authenticated_users_only = False


class TokenPermissions(Permissions):
    """For views which allow authorization via special token"""

    token_permissions = frozenset()
    token_methods = permissions.SAFE_METHODS

    def _has_token(self, request):
        """Is this request authenticated via a token
        Allow if method is in self.token_methods
        Allow if token is authorized with all permissions in self.token_permissions
        """
        return (
            request.method in self.token_methods
            and hasattr(request, "auth")
            and request.auth is not None
            and self.token_permissions.issubset(request.auth["permissions"])
        )

    def has_permission(self, request, view):
        """
        Allow token authed request to contiue to object check
        """
        if self._has_token(request):
            return True
        else:
            return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if self._has_token(request):
            return True
        else:
            return super().has_object_permission(request, view, obj)


class DocumentPermissions(TokenPermissions):
    """Allow the processing functions to update documents"""

    token_permissions = {"processing"}
    token_methods = ["PUT", "PATCH"]


class DocumentErrorPermissions(TokenPermissions):
    """Alow the processing functions to create errors"""

    token_permissions = {"processing"}
    token_methods = ["POST"]
