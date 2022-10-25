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
            and request.auth is not None
            and self.token_permissions.issubset(request.auth.get("permissions", []))
        )


class DocumentTokenPermissions(TokenPermissions):
    """Allow the processing functions to update documents"""

    token_permissions = {"processing"}
    token_methods = ["PUT", "PATCH"]


class DocumentErrorTokenPermissions(TokenPermissions):
    """Alow the processing functions to create errors"""

    token_permissions = {"processing"}
    token_methods = ["POST"]


class DocumentPostProcessPermissions(TokenPermissions):
    """Alow the processing functions to reach post-processing routes"""

    token_permissions = {"processing"}
    token_methods = ["POST"]


class ProjectPermissions(TokenPermissions):
    """Allow the processing functions to view projects"""

    token_permissions = {"processing"}
    token_methods = ["GET"]


class SidekickPermissions(TokenPermissions):
    """Allow the processing functions to update sidekick"""

    token_permissions = {"processing"}
    token_methods = ["PUT", "PATCH"]


class OrganizationAICreditsPermissions(TokenPermissions):
    """Alow the processing functions to reach organization AI credit routes"""

    token_permissions = {"processing"}
    token_methods = ["POST"]
