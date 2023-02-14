# Django
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# Third Party
from rest_flex_fields import FlexFieldsModelSerializer

# DocumentCloud
from documentcloud.entities.models import Entity, EntityOccurrence


class EntitySerializer(FlexFieldsModelSerializer):
    def validate_wikidata_id(self, value):
        if self.instance and self.instance.wikidata_id != value:
            raise serializers.ValidationError(
                {"wikidata_id": "Once created, wikidata_id cannot be changed."}
            )
        return value

    class Meta:
        model = Entity
        fields = [
            "id",
            "wikidata_id",
            "wikipedia_url",
            "name",
            "localized_names",
            "user",
            "description",
            "created_at",
            "updated_at",
            "access",
        ]
        extra_kwargs = {
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
            "wikidata_id": {"required": True},
            "wikipedia_url": {"read_only": True},
            "name": {"read_only": True},
            "localized_names": {"read_only": True},
            "description": {"read_only": True},
            "user": {"read_only": True},
            "access": {"read_only": True},
        }
        expandable_fields = {
            "user": ("documentcloud.users.UserSerializer", {}),
        }


class EntityOccurrenceSerializer(serializers.ModelSerializer):
    entity = EntitySerializer()
    occurrences = serializers.SerializerMethodField(
        label=_("Occurrences"),
        help_text=EntityOccurrence._meta.get_field("occurrences").help_text,
    )

    class Meta:
        model = EntityOccurrence
