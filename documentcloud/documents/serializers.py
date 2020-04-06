# Django
from django.conf import settings
from django.db.models.query import QuerySet
from django.utils.translation import ugettext_lazy as _
from rest_framework import exceptions, serializers
from rest_framework.relations import ManyRelatedField

# Standard Library
import logging
import sys

# Third Party
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
from documentcloud.drf_bulk.serializers import BulkListSerializer
from documentcloud.projects.models import Project

logger = logging.getLogger(__name__)


class PageNumberValidationMixin:
    def validate_page_number(self, value):
        view = self.context.get("view")
        document = Document.objects.get(pk=view.kwargs["document_pk"])
        if value >= document.page_count or value < 0:
            raise serializers.ValidationError("Must be a valid page for the document")
        return value


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
    force_ocr = serializers.BooleanField(
        label=_("Force OCR"),
        write_only=True,
        required=False,
        help_text=_(
            "Force OCR on this document.  Only use if `file_url` is set, "
            "otherwise should set `force_url` on call to processing endpoint."
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

    edit_access = serializers.SerializerMethodField(
        label=_("Edit Access"),
        read_only=True,
        help_text=_("Does the current user have edit access to this document"),
    )

    projects = serializers.PrimaryKeyRelatedField(
        many=True,
        required=False,
        queryset=Project.objects.none(),
        help_text=_("Projects this document belongs to"),
    )

    class Meta:
        model = Document
        list_serializer_class = BulkListSerializer
        fields = [
            "id",
            "access",
            "asset_url",
            "created_at",
            "data",
            "description",
            "edit_access",
            "file_url",
            "force_ocr",
            "language",
            "organization",
            "page_count",
            "page_spec",
            "presigned_url",
            "projects",
            "related_article",
            "remaining",
            "published_url",
            "slug",
            "source",
            "status",
            "title",
            "updated_at",
            "user",
        ]
        extra_kwargs = {
            "created_at": {"read_only": True},
            "description": {"required": False},
            "id": {"read_only": False, "required": False},
            "language": {"default": Language.english},
            "organization": {"read_only": True},
            "page_count": {"read_only": True},
            "page_spec": {"read_only": True},
            "related_article": {"required": False},
            "published_url": {"required": False},
            "slug": {"read_only": True},
            "source": {"required": False},
            "updated_at": {"read_only": True},
            "user": {"read_only": True},
        }
        expandable_fields = {
            "user": ("documentcloud.users.UserSerializer", {}),
            "organization": ("documentcloud.organizations.OrganizationSerializer", {}),
            "projects": ("documentcloud.projects.ProjectSerializer", {"many": True}),
            "sections": ("documentcloud.documents.SectionSerializer", {"many": True}),
            "notes": ("documentcloud.documents.NoteSerializer", {"many": True}),
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

        if not request or (
            "remaining" not in request.GET and "remaining" in self.fields
        ):
            # only show remaining field if it was requested
            del self.fields["remaining"]

        if (
            request
            and request.user
            # check that projects is a field and not expanded into a serializer
            and isinstance(self.fields["projects"], ManyRelatedField)
        ):
            self.fields[
                "projects"
            ].child_relation.queryset = Project.objects.get_editable(request.user)

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

    def validate_projects(self, value):
        if self.instance and value:
            raise serializers.ValidationError(
                "You may not update `projects` directly, please use the projects API"
            )
        return value

    def validate_force_ocr(self, value):
        if self.instance and value:
            raise serializers.ValidationError("You may not update `force_ocr`")
        return value

    def validate_data(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("`data` must be a JSON object")

        # wrap any lone strings in lists
        value = {k: [v] if isinstance(v, str) else v for k, v in value.items()}

        if not all(isinstance(v, list) for v in value.values()):
            raise serializers.ValidationError(
                "`data` JSON object must have arrays for values of all top level "
                "object properties"
            )

        if not all(isinstance(v, str) for v_ in value.values() for v in v_):
            raise serializers.ValidationError(
                "`data` JSON object must have strings for all values within the lists"
                "f top level object properties"
            )

        return value

    def validate(self, attrs):
        if attrs.get("force_ocr") and "file_url" not in attrs:
            raise serializers.ValidationError(
                "`force_ocr` may only be used if `file_url` is set"
            )
        return attrs

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


class NoteSerializer(PageNumberValidationMixin, FlexFieldsModelSerializer):
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
            "user": ("documentcloud.users.UserSerializer", {}),
            "organization": ("documentcloud.organizations.OrganizationSerializer", {}),
        }

    def validate_access(self, value):
        request = self.context.get("request")
        view = self.context.get("view")
        document = Document.objects.get(pk=view.kwargs["document_pk"])
        if value in (Access.public, Access.organization) and not request.user.has_perm(
            "documents.change_document", document
        ):
            raise exceptions.PermissionDenied(
                "You may only create public or draft notes on documents you have "
                "edit access to"
            )
        return value

    def validate(self, attrs):
        """Check the access level and coordinates"""
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


class SectionSerializer(PageNumberValidationMixin, serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ["id", "page_number", "title"]

    def validate_page_number(self, value):
        value = super().validate_page_number(value)

        view = self.context.get("view")
        document = Document.objects.get(pk=view.kwargs["document_pk"])
        if document.sections.filter(page_number=value).exists():
            raise serializers.ValidationError(
                f"You may not add more than one section to a page"
            )
        return value

    def validate(self, attrs):
        """Check the permissions"""
        request = self.context.get("request")
        view = self.context.get("view")
        document = Document.objects.get(pk=view.kwargs["document_pk"])
        if not request.user.has_perm("documents.change_document", document):
            raise exceptions.PermissionDenied(
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


class RedactionSerializer(PageNumberValidationMixin, serializers.Serializer):
    # pylint: disable=abstract-method
    x1 = serializers.FloatField(min_value=0, max_value=1)
    x2 = serializers.FloatField(min_value=0, max_value=1)
    y1 = serializers.FloatField(min_value=0, max_value=1)
    y2 = serializers.FloatField(min_value=0, max_value=1)
    page_number = serializers.IntegerField(min_value=0)

    def validate(self, attrs):
        if attrs["x1"] >= attrs["x2"]:
            raise serializers.ValidationError("`x1` must be less than `x2`")
        if attrs["y1"] >= attrs["y2"]:
            raise serializers.ValidationError("`y1` must be less than `y2`")
        return attrs
