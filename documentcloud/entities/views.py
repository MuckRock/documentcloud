# Django
from rest_framework import permissions, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse

# DocumentCloud
from documentcloud.entities.permissions import IsOwnerOrReadOnly

# Local
from .models import Entity
from .serializers import EntitySerializer


class EntityViewSet(viewsets.ModelViewSet):
    serializer_class = EntitySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = Entity.objects.all()
        wikidata_id = self.request.query_params.get("wikidata_id")
        name = self.request.query_params.get("name")

        if wikidata_id:
            queryset = queryset.filter(wikidata_id=wikidata_id)
        if name:
            queryset = queryset.filter(name=name)

        return queryset

    # def perform_create(self, serializer):
    #     # Don't set if public
    #     # Put in serializer, get rid of this.
    #     serializer.save(owner=self.request.user)

    # def get_permissions(self):
    #     """
    #     Instantiates and returns the list of permissions that this view requires.
    #     """
    #     permission_classes = self.permission_classes
    #     if self.action in ["update", "partial_update", "delete"]:
    #         permission_classes = [
    #             permissions.IsAuthenticatedOrReadOnly,
    #             IsOwnerOrReadOnly,
    #         ]
    #     return [permission() for permission in permission_classes]
