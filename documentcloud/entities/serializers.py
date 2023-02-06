# Django

# Third Party
from rest_flex_fields import FlexFieldsModelSerializer

# Local
from .models import Entity


class EntitySerializer(FlexFieldsModelSerializer):
    # entities = serializers.PrimaryKeyRelatedField(
    #     many=True, queryset=Entity.objects.all()
    # )
    # Return a full user object like in documents.
    # Make access readonly, set it via wikidata_id check.
    # validator to make sure wikidata_id is never changed.

    class Meta:
        model = Entity
        fields = [
            "id",
            "wikidata_id",
            "wikipedia_url",
            "name",
            "localized_names",
            "owner",
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
            "owner": {"read_only": True},
            "access": {"read_only": True},
        }
        expandable_fields = {
            "owner": ("documentcloud.users.UserSerializer", {}),
        }
