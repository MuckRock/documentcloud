# Django
from django.utils.decorators import method_decorator
from rest_framework import exceptions, serializers, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import SAFE_METHODS

# Standard Library
from functools import lru_cache

# Third Party
from django_filters import rest_framework as django_filters

# DocumentCloud
from documentcloud.documents.decorators import conditional_cache_control
from documentcloud.documents.models import Document
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
                "wikidata_id": ["exact", "in"],
                "name": ["exact"],
            }

    filterset_class = Filter


@method_decorator(conditional_cache_control(no_cache=True), name="dispatch")
class EntityOccurrenceViewSet(viewsets.ModelViewSet):
    serializer_class = EntityOccurrenceSerializer
    queryset = EntityOccurrence.objects.none()
    lookup_field = "entity_id"
    permit_list_expands = ["entity"]

    @lru_cache()
    def get_queryset(self):
        self.document = get_object_or_404(
            Document.objects.get_viewable(self.request.user),
            pk=self.kwargs["document_pk"],
        )
        # TODO do we need to filter out private entities here?
        return self.document.entities.all()

    @lru_cache()
    def check_edit_document(self):
        if not self.request.user.has_perm("documents.change_document", self.document):
            raise exceptions.PermissionDenied(
                "You do not have permission to edit entities on this document"
            )

    def check_permissions(self, request):
        """Add an additional check that you can edit the document before
        allowing the user to change an entity within a document
        """
        super().check_permissions(request)
        if request.method not in SAFE_METHODS:
            self.check_edit_document()

    def perform_create(self, serializer):
        """Specify the document"""
        document = Document.objects.get(pk=self.kwargs["document_pk"])
        serializer.save(document=document)

    class Filter(django_filters.FilterSet):
        wikidata_id = django_filters.CharFilter(field_name="entity__wikidata_id")
        name = django_filters.CharFilter(field_name="entity__name")

        class Meta:
            model = EntityOccurrence
            fields = []

    filterset_class = Filter
