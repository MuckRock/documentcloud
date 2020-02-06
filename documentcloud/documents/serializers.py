# Django
from django.conf import settings
from django.db.models.query import QuerySet
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers

# Standard Library
import logging
import sys

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

logger = logging.getLogger(__name__)


class DocumentListSerializer(serializers.ListSerializer):
    def update(self, instance, validated_data):
        # Maps for id->instance and id->data item.
        doc_mapping = {doc.id: doc for doc in instance}
        data_mapping = {item["id"]: item for item in validated_data}

        # Perform creations and updates.
        ret = []
        for doc_id, data in data_mapping.items():
            doc = doc_mapping.get(doc_id)
            if doc:
                ret.append(self.child.update(doc, data))

        return ret

    def validate(self, attrs):
        if len(attrs) > settings.REST_BULK_LIMIT:
            raise serializers.ValidationError(
                f"Bulk API operations are limited to {settings.REST_BULK_LIMIT} "
                "documents at a time"
            )
        return attrs


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
        help_text=_("A publically accessible URL to the file to upload"),
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

    edit_access = serializers.SerializerMethodField(
        label=_("Edit Access"),
        read_only=True,
        help_text=_("Does the current user have edit access to this document"),
    )

    class Meta:
        model = Document
        list_serializer_class = DocumentListSerializer
        fields = [
            "id",
            "access",
            "asset_url",
            "created_at",
            "data",
            "description",
            "edit_access",
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
            "id": {
                "read_only": False,
                "required": False,
            },  # XXX make sure doesnt affect non bulk
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
        is_list = isinstance(self.instance, (list, QuerySet))
        is_document = isinstance(self.instance, Document)

        is_owner = is_create or (
            is_document and request and self.instance.user == request.user
        )
        has_file_url = (
            not is_list
            and hasattr(self, "initial_data")
            and isinstance(self.initial_data, dict)  # guard against bulk creations
            and self.initial_data.get("file_url")
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
        except RequestException as exc:
            logger.warning(
                "Error getting progress for document %d, exception %s",
                obj.pk,
                exc,
                exc_info=sys.exc_info(),
            )
            return {"texts": None, "images": None}

    def get_edit_access(self, obj):
        request = self.context.get("request")
        if not request:
            return False
        return request.user.has_perm("documents.change_document", obj)


class DocumentErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentError
        fields = ["id", "created_at", "message"]
        extra_kwargs = {"created_at": {"read_only": True}}


class NoteSerializer(FlexFieldsModelSerializer):
    access = ChoiceField(
        Access,
        default=Access.private,
        help_text=Note._meta.get_field("access").help_text,
    )
    edit_access = serializers.SerializerMethodField(
        label=_("Edit Access"),
        read_only=True,
        help_text=_("Does the current user have edit access to this note"),
    )

    class Meta:
        model = Note
        fields = [
            "id",
            "user",
            "organization",
            "page_number",
            "access",
            "edit_access",
            "title",
            "content",
            "x1",
            "x2",
            "y1",
            "y2",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "created_at": {"read_only": True},
            "organization": {"read_only": True},
            "updated_at": {"read_only": True},
            "user": {"read_only": True},
            "content": {"required": False},
        }
        expandable_fields = {
            "user": (UserSerializer, {"source": "user"}),
            "organization": (OrganizationSerializer, {"source": "organization"}),
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

    def validate_page(self, value):
        view = self.context.get("view")
        document = Document.objects.get(pk=view.kwargs["document_pk"])
        if value >= document.page_count:
            raise serializers.ValidationError("Must be a valid page for the document")
        return value

    def validate(self, attrs):
        """Check the access level and coordinates"""
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

        # Bounds should either all be set or not set at all
        if all(attr not in attrs for attr in ("x1", "x2", "y1", "y2")):
            return attrs

        # If bounds were set, ensure they are in range
        if attrs["x1"] >= attrs["x2"]:
            raise serializers.ValidationError("`x1` must be less than `x2`")
        if attrs["y1"] >= attrs["y2"]:
            raise serializers.ValidationError("`y1` must be less than `y2`")
        return attrs

    def get_edit_access(self, obj):
        request = self.context.get("request")
        if not request:
            return False
        return request.user.has_perm("documents.change_note", obj)


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


class RedactionSerializer(serializers.Serializer):
    # pylint: disable=abstract-method
    x1 = serializers.FloatField(min_value=0, max_value=1)
    x2 = serializers.FloatField(min_value=0, max_value=1)
    y1 = serializers.FloatField(min_value=0, max_value=1)
    y2 = serializers.FloatField(min_value=0, max_value=1)
    page = serializers.IntegerField(min_value=0)

    def validate(self, attrs):
        if attrs["x1"] >= attrs["x2"]:
            raise serializers.ValidationError("`x1` must be less than `x2`")
        if attrs["y1"] >= attrs["y2"]:
            raise serializers.ValidationError("`y1` must be less than `y2`")
        return attrs

    def validate_page(self, value):
        view = self.context.get("view")
        document = Document.objects.get(pk=view.kwargs["document_pk"])
        if value >= document.page_count:
            raise serializers.ValidationError("Must be a valid page for the document")
        return value
