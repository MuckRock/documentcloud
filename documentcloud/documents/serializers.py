# Django
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers

# Third Party
import requests
from requests.exceptions import RequestException
from rest_flex_fields import FlexFieldsModelSerializer

# DocumentCloud
from documentcloud.common.environment import httpsub, storage
from documentcloud.core.choices import Language
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.fields import ChoiceField
from documentcloud.documents.models import (
    Document,
    DocumentError,
    Entity,
    EntityDate,
    Note,
    Section,
)
from documentcloud.organizations.serializers import OrganizationSerializer
from documentcloud.users.serializers import UserSerializer


class DocumentSerializer(FlexFieldsModelSerializer):

    presigned_url = serializers.SerializerMethodField(
        label=_("Presigned URL"),
        read_only=True,
        help_text=_("The presigned URL to upload the file to"),
    )
    file_url = serializers.URLField(
        label=_("File URL"),
        write_only=True,
        required=False,
        help_text=_(
            "A publically accessible URL to the file to upload - use this field or "
            "`file`"
        ),
    )
    access = ChoiceField(
        Access,
        default=Access.private,
        help_text=Document._meta.get_field("access").help_text,
    )
    status = ChoiceField(
        Status, read_only=True, help_text=Document._meta.get_field("status").help_text
    )

    remaining = serializers.SerializerMethodField(
        label=_("Text and image pages remaining"),
        read_only=True,
        help_text=_(
            "How many pages are left to be processed - only present during processing"
        ),
    )

    class Meta:
        model = Document
        fields = [
            "id",
            "access",
            "asset_url",
            "created_at",
            "data",
            "description",
            "file_url",
            "language",
            "organization",
            "page_count",
            "page_spec",
            "presigned_url",
            "remaining",
            "slug",
            "source",
            "status",
            "title",
            "updated_at",
            "user",
        ]
        extra_kwargs = {
            "created_at": {"read_only": True},
            "data": {"read_only": True},
            "description": {"required": False},
            "language": {"default": Language.english},
            "organization": {"read_only": True},
            "page_count": {"read_only": True},
            "page_spec": {"read_only": True},
            "slug": {"read_only": True},
            "source": {"required": False},
            "updated_at": {"read_only": True},
            "user": {"read_only": True},
        }
        expandable_fields = {
            "user": (UserSerializer, {"source": "user"}),
            "organization": (OrganizationSerializer, {"source": "organization"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        context = kwargs.get("context", {})
        request = context.get("request")
        if self._authenticate_processing(request):
            # If this request is from our serverless processing functions,
            # make the following fields writable
            for field in ["page_count", "page_spec", "status"]:
                self.fields[field].read_only = False

        if not isinstance(self.instance, Document) or self.instance.status not in (
            Status.pending,
            Status.readable,
        ):
            # remaining field or for processing documents only
            del self.fields["remaining"]

        is_create = self.instance is None
        is_list = isinstance(self.instance, list)
        is_document = isinstance(self.instance, Document)

        is_owner = is_create or (
            is_document and request and self.instance.user == request.user
        )
        has_file_url = hasattr(self, "initial_data") and self.initial_data.get(
            "file_url"
        )
        has_file = is_document and self.instance.status != Status.nofile
        if (is_create and has_file_url) or is_list or has_file or not is_owner:
            # only show presigned url if we are creating a new document without a
            # file url, or the document has not had a file uploaded yet
            del self.fields["presigned_url"]

    def _authenticate_processing(self, request):
        """Check the requests Authorization header for our special token"""
        if not request or not hasattr(request, "auth") or request.auth is None:
            return False

        return "processing" in request.auth["permissions"]

    def validate_file_url(self, value):
        if self.instance and value:
            raise serializers.ValidationError("You may not update `file_url`")
        return value

    def get_presigned_url(self, obj):
        """Return the presigned URL to upload the file to"""
        return storage.presign_url(obj.doc_path, "put_object")

    def get_remaining(self, obj):
        """Get the progress data from the serverless function"""
        try:
            response = httpsub.post(
                settings.PROGRESS_URL,
                json={"doc_id": obj.pk},
                timeout=settings.PROGRESS_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except RequestException:
            return {"texts_remaining": None, "images_remaining": None}


class DocumentErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentError
        fields = ["id", "created_at", "message"]
        extra_kwargs = {"created_at": {"read_only": True}}


class NoteSerializer(serializers.ModelSerializer):
    access = ChoiceField(
        Access,
        default=Access.private,
        help_text=Note._meta.get_field("access").help_text,
    )

    class Meta:
        model = Note
        fields = [
            "id",
            "user",
            "organization",
            "page_number",
            "access",
            "title",
            "content",
            "top",
            "left",
            "bottom",
            "right",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "created_at": {"read_only": True},
            "organization": {"read_only": True},
            "updated_at": {"read_only": True},
            "user": {"read_only": True},
        }

    def validate_access(self, value):
        if (
            self.instance
            and self.instance.access == Access.private
            and value != Access.private
        ):
            raise serializers.ValidationError(
                "May not make a private note public or draft"
            )
        if (
            self.instance
            and self.instance.access != Access.private
            and value == Access.private
        ):
            raise serializers.ValidationError(
                "May not make a public or draft note private"
            )
        return value

    def validate(self, attrs):
        """Check the access level"""
        request = self.context.get("request")
        view = self.context.get("view")
        document = Document.objects.get(pk=view.kwargs["document_pk"])
        if attrs.get("access") in (
            Access.public,
            Access.organization,
        ) and not request.user.has_perm("documents.change_document", document):
            raise serializers.ValidationError(
                "You may only create public or draft notes on documents you have "
                "edit access to"
            )
        return attrs


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ["id", "page_number", "title"]

    def validate(self, attrs):
        """Check the permissions"""
        request = self.context.get("request")
        view = self.context.get("view")
        document = Document.objects.get(pk=view.kwargs["document_pk"])
        if not request.user.has_perm("documents.change_document", document):
            raise serializers.ValidationError(
                "You may only create sections on documents you have edit access to"
            )
        return attrs


class EntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Entity
        fields = ["kind", "value", "relevance", "occurrences"]


class EntityDateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntityDate
        fields = ["date", "occurrences"]


class DataSerializer(serializers.Serializer):
    # pylint: disable=abstract-method
    values = serializers.ListSerializer(child=serializers.CharField(max_length=200))


class DataAddRemoveSerializer(serializers.Serializer):
    # pylint: disable=abstract-method
    values = serializers.ListSerializer(
        required=False, child=serializers.CharField(max_length=200)
    )
    remove = serializers.ListSerializer(
        required=False, child=serializers.CharField(max_length=200)
    )
