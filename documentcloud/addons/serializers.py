# Django
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# Third Party
import jsonschema
from rest_flex_fields import FlexFieldsModelSerializer

# DocumentCloud
from documentcloud.addons.models import AddOn, AddOnEvent, AddOnRun
from documentcloud.common.environment import storage
from documentcloud.documents.choices import Access
from documentcloud.documents.fields import ChoiceField


class AddOnSerializer(FlexFieldsModelSerializer):
    access = ChoiceField(
        Access,
        default=Access.private,
        help_text=AddOn._meta.get_field("access").help_text,
        read_only=True,
    )
    active_w = serializers.BooleanField(
        label=_("Active"),
        default=False,
        write_only=True,
        help_text=_("Show this add-on in your add-on menu"),
    )
    active = serializers.SerializerMethodField(
        label=_("Active"), help_text=_("Show this add-on in your add-on menu")
    )
    user = serializers.PrimaryKeyRelatedField(
        read_only=True, source="github_account.user"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        view = self.context.get("view")
        request = self.context.get("request")

        active_w = self.fields.pop("active_w", None)
        # for updates which include setting active
        # change the active field to the writable active field
        if (
            active_w is not None
            and view
            and view.action in ("update", "partial_update")
            and hasattr(self, "initial_data")
            and "active" in self.initial_data
        ):
            self.fields["active"] = active_w

        if (
            request
            and request.user.is_authenticated
            and view.action in ("update", "partial_update")
            and self.instance
            and self.instance.user == request.user
        ):
            self.fields["organization"].read_only = False
            self.fields["organization"].queryset = request.user.organizations.all()

    def get_active(self, obj):

        if hasattr(obj, "active"):
            # pre calculate active for efficiency
            return obj.active

        request = self.context.get("request")
        if not request:
            return False

        return request.user.active_addons.filter(pk=obj.pk).exists()

    class Meta:
        model = AddOn
        fields = [
            "id",
            "user",
            "organization",
            "access",
            "name",
            "repository",
            "parameters",
            "created_at",
            "updated_at",
            "active_w",
            "active",
            "default",
            "featured",
        ]
        extra_kwargs = {
            "organization": {"read_only": True},
            "name": {"read_only": True},
            "repository": {"read_only": True},
            "parameters": {"read_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
            "default": {"read_only": True},
            "featured": {"read_only": True},
        }


class AddOnRunSerializer(FlexFieldsModelSerializer):

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

    file_expires_at = serializers.SerializerMethodField(
        label=_("File Expires At"),
        read_only=True,
        help_text=_("Timestamp when the uploaded file will expire"),
    )

    parameters = serializers.JSONField(
        label=_("Parameters"),
        write_only=True,
        help_text=_("The user supplied parameters"),
    )

    class Meta:
        model = AddOnRun
        fields = [
            "uuid",
            "addon",
            "user",
            "status",
            "progress",
            "message",
            "presigned_url",
            "file_url",
            "file_expires_at",
            "file_name",
            "dismissed",
            "parameters",
            "rating",
            "comment",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "uuid": {"read_only": True},
            "addon": {"queryset": AddOn.objects.none()},
            "user": {"read_only": True},
            "status": {"read_only": True},
            "file_name": {"write_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }
        expandable_fields = {"addon": ("documentcloud.addons.AddOnSerializer", {})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        context = kwargs.get("context", {})
        request = context.get("request")
        self._expires_at = {}
        if request and request.user:
            self.fields["addon"].queryset = AddOn.objects.get_viewable(request.user)

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
        expires_at = self.get_file_expires_at(obj)
        if expires_at is None:
            return None
        if obj.file_name and timezone.now() < self.get_file_expires_at(obj):
            return settings.DOCCLOUD_API_URL + reverse(
                "addon-run-file", args=[obj.uuid]
            )
        else:
            return None

    def get_file_expires_at(self, obj):
        if obj.file_name and obj.file_name is not in self._expires_at:
            self._expires_at[obj.file_name] = storage.get_expires_at(obj.file_path())
        return self._expires_at[obj.file_name]

    def validate_addon(self, value):
        if self.instance and value:
            raise serializers.ValidationError("You may not update `addon`")
        return value

    def validate_progress(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("`progress` must be between 0 and 100")
        return value

    def validate(self, attrs):
        """Validate the parameters using jsonschema"""
        if "parameters" in attrs:
            try:
                jsonschema.validate(
                    instance=attrs.pop("parameters"), schema=attrs["addon"].parameters
                )
            except jsonschema.exceptions.ValidationError as exc:
                raise serializers.ValidationError(exc.message)
        return attrs


class AddOnEventSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = AddOnEvent
        fields = [
            "id",
            "addon",
            "user",
            "parameters",
            "event",
            "parameters",
            "scratch",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "addon": {"queryset": AddOn.objects.none()},
            "user": {"read_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }
        expandable_fields = {"addon": ("documentcloud.addons.AddOnSerializer", {})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        context = kwargs.get("context", {})
        request = context.get("request")
        if request and request.user:
            self.fields["addon"].queryset = AddOn.objects.get_viewable(request.user)
