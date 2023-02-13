# Django
from rest_framework import permissions, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse

# DocumentCloud
from documentcloud.entities.models import Entity, EntityOccurrence2
from documentcloud.entities.permissions import IsOwnerOrReadOnly
from documentcloud.entities.serializers import (
    EntityOccurrence2Serializer,
    EntitySerializer,
)


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


class EntityOccurrence2ViewSet(viewsets.ModelViewSet):
    serializer_class = EntityOccurrence2Serializer

    querystring_key_to_filter_key_dict = {
        "entity_name": "entity__name",
        "wikidata_id": "entity__wikidata_id",
        "entity": "entity__id",
        "document": "document__id",
    }

    def get_queryset(self):
        queryset = EntityOccurrence2.objects.all()
        filter_kwargs = {}
        for key in EntityOccurrence2ViewSet.querystring_key_to_filter_key_dict.keys():
            value = self.request.query_params.get(key)
            if value:
                filter_kwargs[
                    EntityOccurrence2ViewSet.querystring_key_to_filter_key_dict[key]
                ] = value

        if len(filter_kwargs.values) > 0:
            queryset = queryset.filter(**filter_kwargs)

        return queryset
