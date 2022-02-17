# Django
from rest_framework import serializers

# DocumentCloud
from documentcloud.plugins.models import Plugin, PluginRun


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


class PluginRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = PluginRun
        fields = ["uuid", "plugin", "user", "status", "created_at", "updated_at"]
        extra_kwargs = {
            "uuid": {"read_only": True},
            "user": {"read_only": True},
            "status": {"read_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }

    def validate_plugin(self, value):
        if self.instance and value:
            raise serializers.ValidationError("You may not update `plugin`")
        return value
