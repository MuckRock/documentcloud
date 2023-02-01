# Django
from rest_framework import serializers

# Local
from .models import Entity


class EntitySerializer(serializers.HyperlinkedModelSerializer):
    # entities = serializers.PrimaryKeyRelatedField(
    #     many=True, queryset=Entity.objects.all()
    # )
    # Use document's serializer
    owner = serializers.ReadOnlyField(source="owner.username")
    wikipedia_url = serializers.ReadOnlyField()
    name = serializers.ReadOnlyField()
    localized_names = serializers.ReadOnlyField()
    description = serializers.ReadOnlyField()

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
        # TODO: wikidata_id should be read-only, but only after creation.
