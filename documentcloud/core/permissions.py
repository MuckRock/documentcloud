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
        print("CHECKING PERMISSION")
        print(request.user)
        print(request.auth)
        if request.user.is_authenticated:
            print("AUTHENTICATED")
            return True
        elif (
            hasattr(request, "auth")
            and request.auth is not None
            and request.method in ["PUT", "PATCH"]
        ):
            print("AUTH2")
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
        print("VALID TOKEN", valid_token)
        print("HAS ATTR", hasattr(request, "auth"))
        print("REQUEST USER", request.user)
        print("REQUEST AUTH", request.auth)
        print("REQUEST AUTH PERMISSIONS", request.auth['permissions'] if request.auth else None)
        if (
            valid_token
            and request.method in ["PUT", "PATCH"]
            and isinstance(obj, Document)
        ):
            print("YUP")
            return True
        else:
            print("CHECKING WITH SUPER")
            return super().has_object_permission(request, view, obj)
