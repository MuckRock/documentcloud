# Django
from rest_framework import serializers, viewsets

# Third Party
from django_filters import rest_framework as django_filters

# DocumentCloud
from documentcloud.drf_bulk.views import BulkCreateModelMixin
from documentcloud.entities.choices import EntityAccess
from documentcloud.entities.models import Entity, EntityOccurrence
from documentcloud.entities.serializers import (
    EntityOccurrenceSerializer,
    EntitySerializer,
)


class EntityViewSet(BulkCreateModelMixin, viewsets.ModelViewSet):
    serializer_class = EntitySerializer
    queryset = Entity.objects.none()

    def get_queryset(self):
        return Entity.objects.get_viewable(self.request.user)

    def perform_create(self, serializer):
        if serializer.validated_data.get("access") == EntityAccess.private:
            # set the user on prviate entities
            entity = serializer.save(user=self.request.user)
        else:
            # lookup wikidata on public entities
            entity = serializer.save()
            try:
                entity.lookup_wikidata()
                entity.save()
            except ValueError:
                raise serializers.ValidationError("Invalid `wikidata_id`")

    def bulk_perform_create(self, serializer):
        first = serializer.validated_data[0]
        if not all(
            d.get("access") == first.get("access") for d in serializer.validated_data
        ):
            raise serializers.ValidationError(
                "Bulk entity creation must all have same `access`"
            )
        if first.get("access") == EntityAccess.private:
            # set the user on prviate entities
            entity = serializer.save(user=self.request.user)
        else:
            # lookup wikidata on public entities
            entities = serializer.save()
            # TODO: do bulk lookups more efficiently (or in the background)
            for entity in entities:
                try:
                    entity.lookup_wikidata()
                    entity.save()
                except ValueError:
                    raise serializers.ValidationError("Invalid `wikidata_id`")

    class Filter(django_filters.FilterSet):
        class Meta:
            model = Entity
            fields = {
                "wikidata_id": ["exact"],
                "name": ["exact"],
            }

    filterset_class = Filter


class EntityOccurrenceViewSet(viewsets.ModelViewSet):
    serializer_class = EntityOccurrenceSerializer

    querystring_key_to_filter_key_dict = {
        "entity_name": "entity__name",
        "wikidata_id": "entity__wikidata_id",
        "entity": "entity__id",
        "document": "document__id",
    }

    def get_queryset(self):
        queryset = EntityOccurrence.objects.all()
        filter_kwargs = {}
        for key in EntityOccurrenceViewSet.querystring_key_to_filter_key_dict.keys():
            value = self.request.query_params.get(key)
            if value:
                filter_kwargs[
                    EntityOccurrenceViewSet.querystring_key_to_filter_key_dict[key]
                ] = value

        if len(filter_kwargs.values) > 0:
            queryset = queryset.filter(**filter_kwargs)

        return queryset
