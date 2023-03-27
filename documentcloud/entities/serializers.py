# Django
from rest_framework import serializers

# Third Party
from rest_flex_fields import FlexFieldsModelSerializer

# DocumentCloud
from documentcloud.documents.models import Document
from documentcloud.drf_bulk.serializers import BulkListSerializer
from documentcloud.entities.choices import EntityAccess
from documentcloud.entities.models import Entity, EntityOccurrence


class EntitySerializer(FlexFieldsModelSerializer):
    class Meta:
        model = Entity
        fields = [
            "access",
            "created_at",
            "description",
            "id",
            "localized_names",
            "metadata",
            "name",
            "updated_at",
            "user",
            "wikidata_id",
            "wikipedia_url",
        ]
        extra_kwargs = {
            "access": {"read_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
            "user": {"read_only": True},
            # TODO remove this as being required to allow private entities to be
            # created
            "wikidata_id": {"required": True},
        }
        expandable_fields = {
            "user": ("documentcloud.users.UserSerializer", {}),
        }

    def validate(self, attrs):
        if "wikidata_id" in attrs:
            # public entity, no other fields may be set
            if len(attrs) > 1:
                raise serializers.ValidationError(
                    "You may not set any other fields if you set `wikidata_id`"
                )
            attrs["access"] = EntityAccess.public
        else:
            # private entity, name is required
            if "name" not in attrs:
                raise serializers.ValidationError(
                    "Name is required for private entities"
                )
            attrs["access"] = EntityAccess.private

        return attrs


class OccurrenceSerializer(serializers.Serializer):
    """Serializer to validate the occurrences field of an EntityOccurrence"""

    page = serializers.IntegerField(min_value=0)
    offset = serializers.IntegerField(min_value=0)
    page_offset = serializers.IntegerField(min_value=0)
    content = serializers.CharField(max_length=200)

    def validate_page(self, value):
        view = self.context.get("view")
        if not view:
            return value
        document = Document.objects.get(pk=view.kwargs["document_pk"])
        if value >= document.page_count:
            raise serializers.ValidationError(
                f"Page number greater then document page count: {document.page_count}"
            )

        return value


class EntityOccurrenceSerializer(FlexFieldsModelSerializer):

    occurrences = OccurrenceSerializer(many=True, required=False)

    class Meta:
        model = EntityOccurrence
        list_serializer_class = BulkListSerializer
        update_lookup_field = "entity"
        fields = ["entity", "relevance", "occurrences"]
        extra_kwargs = {
            "entity": {
                "queryset": Entity.objects.none(),
                "style": {"base_template": "input.html"},
            }
        }
        expandable_fields = {"entity": ("documentcloud.entities.EntitySerializer", {})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user and "entity" in self.fields:
            self.fields["entity"].queryset = Entity.objects.get_viewable(request.user)
