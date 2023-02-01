from documentcloud.entities.permissions import IsOwnerOrReadOnly
from .models import Entity
from rest_framework import viewsets
from rest_framework import permissions
from .serializers import (
    EntitySerializer,
)
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse


class EntityViewSet(viewsets.ModelViewSet):
    queryset = Entity.objects.all()
    serializer_class = EntitySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        permission_classes = self.permission_classes
        if self.action in ["update", "partial_update", "delete"]:
            permission_classes = [
                permissions.IsAuthenticatedOrReadOnly,
                IsOwnerOrReadOnly,
            ]
        return [permission() for permission in permission_classes]


@api_view(["GET"])
def api_root(request, format=None):
    return Response(
        {
            "entities": reverse("entity-list", request=request, format=format),
        }
    )
