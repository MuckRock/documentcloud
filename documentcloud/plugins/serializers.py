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
        fields = [
            "uuid",
            "plugin",
            "user",
            "status",
            "progress",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "uuid": {"read_only": True},
            "user": {"read_only": True},
            "status": {"read_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
            "plugin": {"queryset": Plugin.objects.none()},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        context = kwargs.get("context", {})
        request = context.get("request")
        if request and request.user:
            self.fields["plugin"].queryset = Plugin.objects.get_viewable(request.user)

    def validate_plugin(self, value):
        if self.instance and value:
            raise serializers.ValidationError("You may not update `plugin`")
        return value

    def validate_progress(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("`progress` must be between 0 and 100")
        return value
