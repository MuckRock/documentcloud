from .models import Entity
from rest_framework import serializers
from django.contrib.auth.models import User, Group


class EntitySerializer(serializers.HyperlinkedModelSerializer):
    # entities = serializers.PrimaryKeyRelatedField(
    #     many=True, queryset=Entity.objects.all()
    # )
    # Use document's serializer
    owner = serializers.ReadOnlyField(source="owner.username")
    wikipedia_url = serializers.ReadOnlyField()
    name = serializers.ReadOnlyField()
    description = serializers.ReadOnlyField()

    class Meta:
        model = Entity
        fields = [
            "id",
            "wikidata_id",
            "wikipedia_url",
            "name",
            "owner",
            "description",
            "created_at",
            "updated_at",
            "access",
        ]
        # TODO: wikidata_id should be read-only, but only after creation.


class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "entities"]


class GroupSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Group
        fields = ["url", "name"]
