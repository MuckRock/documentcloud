# Django
from django.db.models import prefetch_related_objects
from django.utils.decorators import method_decorator
from rest_framework import exceptions, serializers, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import SAFE_METHODS

# Standard Library
from functools import lru_cache

# Third Party
from django_filters import rest_framework as django_filters
from drf_spectacular.utils import OpenApiExample, extend_schema
from requests.exceptions import RequestException

# DocumentCloud
from documentcloud.common.wikidata import WikidataEntities
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

    @extend_schema(
        request=None,
        responses={200: EntitySerializer(many=True)},
        examples=[
            OpenApiExample(
                "List Entities",
                description="A request to retrieve a list of entities.",
                value=[
                    {
                        "id": 1,
                        "name": "Common Era",
                        "access": "public",
                        "created_at": "2023-05-18T12:57:50.814203Z",
                        "updated_at": "2023-05-18T12:57:50.815184Z",
                        "description": "modern calendar era",
                        "wikidata_id": "Q208141",
                        "wikipedia_url": "https://en.wikipedia.org/wiki/Common_Era",
                        "metadata": {},
                        "user": None,
                    },
                    {
                        "id": 2,
                        "name": "maintenance",
                        "access": "public",
                        "created_at": "2023-05-18T12:57:50.814265Z",
                        "updated_at": "2023-05-18T12:57:50.815219Z",
                        "description": "Involves repairing",
                        "wikidata_id": "Q1043452",
                        "wikipedia_url": "https://en.wikipedia.org/wiki/Maintenance",
                        "metadata": {},
                        "user": None,
                    },
                ],
                response_only=True,
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=None,
        responses={200: EntitySerializer},
        examples=[
            OpenApiExample(
                "Retrieve Entity",
                description="A response for a retrieve request of a specific entity by ID.",  # pylint:disable=line-too-long
                value={
                    "id": 1,
                    "name": "Common Era",
                    "access": "public",
                    "created_at": "2023-05-18T12:57:50.814203Z",
                    "updated_at": "2023-05-18T12:57:50.815184Z",
                    "description": "modern calendar era",
                    "wikidata_id": "Q208141",
                    "wikipedia_url": "https://en.wikipedia.org/wiki/Common_Era",
                    "metadata": {},
                    "user": None,
                },
                response_only=True,
            ),
        ],
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        request=EntitySerializer,
        responses={201: EntitySerializer},
        examples=[
            OpenApiExample(
                "Create Entity",
                description="A request to create a new entity.",
                value={
                    "name": "New Entity",
                    "access": "public",
                    "description": "A new entity description",
                    "wikidata_id": "Q123456",
                    "wikipedia_url": "https://en.wikipedia.org/wiki/New_Entity",
                    "metadata": {},
                    "user": None,
                },
                response_only=True,
            ),
        ],
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(
        request=EntitySerializer,
        responses={200: EntitySerializer},
        examples=[
            OpenApiExample(
                "Update Entity",
                description="A request to update a specific entity.",
                value={
                    "wikidata_id": "Q999999",
                    "metadata": {"new_key": "new_value"},
                },
                response_only=True,
            ),
        ],
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @extend_schema(
        request=EntitySerializer,
        responses={200: EntitySerializer},
        examples=[
            OpenApiExample(
                "Partial Update Entity",
                description="A request to partially update a specific entity.",
                value={"id": 1, "wikidata_id": "Q999999"},
                response_only=True,
            ),
        ],
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    def get_queryset(self):
        return Entity.objects.get_viewable(self.request.user)

    def perform_create(self, serializer):

        bulk = hasattr(serializer, "many") and serializer.many
        if bulk:
            first = serializer.validated_data[0]
            if not all(
                d.get("access") == first.get("access")
                for d in serializer.validated_data
            ):
                raise serializers.ValidationError(
                    "Bulk entity creation must all have same `access`"
                )
        else:
            first = serializer.validated_data

        if first.get("access") == EntityAccess.private:
            # set the user on prviate entities
            entities = serializer.save(user=self.request.user)
        else:
            # lookup wikidata on public entities
            entities = serializer.save()
            if not bulk:
                entities = [entities]

            try:
                wikidata = WikidataEntities(entities)
                wikidata.create_translations()
                prefetch_related_objects(entities, "translations")
            except ValueError as exc:
                raise serializers.ValidationError(exc.args[0])
            except RequestException:
                raise serializers.ValidationError(
                    "Error contacting Wikidata.  Please try again later."
                )

    class Filter(django_filters.FilterSet):
        name = django_filters.CharFilter(
            field_name="translations__name", help_text="The name of the entity"
        )
        wikidata_id = django_filters.CharFilter(
            help_text="The Wikidata ID of the entity"
        )

        class Meta:
            model = Entity
            fields = {
                "wikidata_id": ["exact", "in"],
            }

    filterset_class = Filter


@method_decorator(conditional_cache_control(no_cache=True), name="dispatch")
class EntityOccurrenceViewSet(BulkCreateModelMixin, viewsets.ModelViewSet):
    serializer_class = EntityOccurrenceSerializer
    queryset = EntityOccurrence.objects.none()
    lookup_field = "entity_id"
    permit_list_expands = ["entity"]

    @extend_schema(tags=["document_entities"])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(tags=["document_entities"])
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(tags=["document_entities"])
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @extend_schema(tags=["document_entities"])
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @extend_schema(tags=["document_entities"])
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(tags=["document_entities"])
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @lru_cache()
    def get_queryset(self):
        self.document = get_object_or_404(
            Document.objects.get_viewable(self.request.user),
            pk=self.kwargs["document_pk"],
        )
        # do we need to filter out private entities here?
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
        name = django_filters.CharFilter(field_name="entity__translations__name")

        class Meta:
            model = EntityOccurrence
            fields = []

    filterset_class = Filter
