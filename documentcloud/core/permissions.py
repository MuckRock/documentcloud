# Django
from rest_framework import permissions

# DocumentCloud
from documentcloud.documents.models import Document


class Permissions(permissions.DjangoObjectPermissions):
    """Use Django Object permissions as the base for our Document permissions"""

    def has_permission(self, request, view):
        """Authenticated users permissions will be checked on a per object basis
        Return true here to continue to the object check
        Anonymous users have read-only access
        """
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
            and "processing" in request.auth["permissions"]
        )
        if (
            valid_token
            and request.method in ["PUT", "PATCH"]
            and isinstance(obj, Document)
        ):
            return True
        else:
            return super().has_object_permission(request, view, obj)
