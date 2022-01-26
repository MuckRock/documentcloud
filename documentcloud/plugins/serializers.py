# Django
from rest_framework import serializers

# DocumentCloud
from documentcloud.plugins.models import Plugin


class PluginSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plugin
        fields = [
            "id",
            "user",
            "organization",
            "name",
            "repository",
            "parameters",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "user": {"read_only": True},
            "organization": {"read_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }
