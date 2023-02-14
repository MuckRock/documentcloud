# Django
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# Third Party
from rest_flex_fields import FlexFieldsModelSerializer

# DocumentCloud
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


class EntityOccurrenceSerializer(serializers.ModelSerializer):
    entity = EntitySerializer()
    occurrences = serializers.SerializerMethodField(
        label=_("Occurrences"),
        help_text=EntityOccurrence._meta.get_field("occurrences").help_text,
    )

    class Meta:
        model = EntityOccurrence
