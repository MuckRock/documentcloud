# Django
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# DocumentCloud
from documentcloud.common.environment import storage
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

    presigned_url = serializers.SerializerMethodField(
        label=_("Presigned URL"),
        read_only=True,
        help_text=_("The presigned URL to upload the file to"),
    )

    file_url = serializers.SerializerMethodField(
        label=_("File URL"),
        read_only=True,
        help_text=_("The presigned URL to download the file from"),
    )

    class Meta:
        model = PluginRun
        fields = [
            "uuid",
            "plugin",
            "user",
            "status",
            "progress",
            "presigned_url",
            "file_url",
            "file_name",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "uuid": {"read_only": True},
            "plugin": {"queryset": Plugin.objects.none()},
            "user": {"read_only": True},
            "status": {"read_only": True},
            "file_name": {"write_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        context = kwargs.get("context", {})
        request = context.get("request")
        if request and request.user:
            self.fields["plugin"].queryset = Plugin.objects.get_viewable(request.user)

        if (
            request
            and "upload_file" in request.query_params
            and (not self.instance or not self.instance.file_name)
        ):
            self.upload_file = request.query_params["upload_file"]
        else:
            del self.fields["presigned_url"]

    def get_presigned_url(self, obj):
        return storage.presign_url(obj.file_path(self.upload_file), "put_object")

    def get_file_url(self, obj):
        if obj.file_name:
            return storage.presign_url(obj.file_path(), "get_object")
        else:
            return None

    def validate_plugin(self, value):
        if self.instance and value:
            raise serializers.ValidationError("You may not update `plugin`")
        return value

    def validate_progress(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("`progress` must be between 0 and 100")
        return value