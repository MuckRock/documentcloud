# Django
from django.conf import settings
from django.db.models import prefetch_related_objects
from django.db.models.query import QuerySet
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions, serializers
from rest_framework.relations import ManyRelatedField

# Standard Library
import logging
import re

# Third Party
from rest_flex_fields import FlexFieldsModelSerializer

# DocumentCloud
from documentcloud.common.environment import storage
from documentcloud.core.choices import Language
from documentcloud.core.utils import slugify
from documentcloud.documents.choices import Access, EntityKind, OccurrenceKind, Status
from documentcloud.documents.constants import DATA_KEY_REGEX
from documentcloud.documents.fields import ChoiceField
from documentcloud.documents.models import (
    Document,
    DocumentError,
    Entity,
    EntityDate,
    EntityOccurrence,
    LegacyEntity,
    Note,
    Section,
)
from documentcloud.drf_bulk.serializers import BulkListSerializer
from documentcloud.projects.models import Project
from documentcloud.users.models import User

logger = logging.getLogger(__name__)

DATA_VALUE_LENGTH = 300


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
            "otherwise should set `force_ocr` on call to processing endpoint."
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

    canonical_url = serializers.SerializerMethodField(
        label=_("Canonical URL"),
        read_only=True,
        help_text=_("The canonical URL to access this document"),
    )

    class Meta:
        model = Document
        list_serializer_class = BulkListSerializer
        fields = [
            "id",
            "access",
            "asset_url",
            "canonical_url",
            "created_at",
            "data",
            "description",
            "edit_access",
            "file_hash",
            "file_url",
            "force_ocr",
            "language",
            "organization",
            "original_extension",
            "page_count",
            "page_spec",
            "presigned_url",
            "projects",
            "publish_at",
            "published_url",
            "related_article",
            "slug",
            "source",
            "status",
            "title",
            "updated_at",
            "user",
        ]
        extra_kwargs = {
            "created_at": {"read_only": True},
            "description": {"required": False, "max_length": 4000},
            "file_hash": {"read_only": True},
            "language": {"default": Language.english},
            "organization": {"read_only": True},
            "original_extension": {"default": "pdf"},
            "page_count": {"read_only": True},
            "page_spec": {"read_only": True},
            "publish_at": {"required": False},
            "published_url": {"required": False},
            "related_article": {"required": False},
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
        view = context.get("view")
        user = request and request.user
        is_document = isinstance(self.instance, Document)
        is_list = isinstance(self.instance, (list, QuerySet))

        self._init_readonly(request, view, user)
        self._init_projects_queryset(user)
        self._init_presigned_url(request, user, is_document, is_list)
        self._init_change_ownership(request, user, is_document, is_list)

    def _init_readonly(self, request, view, user):
        """Dynamically alter read only status of fields"""
        if self._authenticate_processing(request):
            # If this request is from our serverless processing functions,
            # make the following fields writable
            for field in ["file_hash", "page_count", "page_spec", "status"]:
                self.fields[field].read_only = False

        if view and view.action in ("bulk_update", "bulk_partial_update"):
            # ID is not read only for bulk updates
            self.fields["id"].read_only = False

        if user and user.is_authenticated and not user.verified_journalist:
            # non-verified journalists may not make documents public
            if "access" in self.fields:
                self.fields["access"].choices.pop(Access.public)
                self.fields["access"].choice_map.pop("public")
            if "publish_at" in self.fields:
                self.fields["publish_at"].read_only = True

    def _init_projects_queryset(self, user):
        """Initalize querysets for valid choices for projects"""
        if (
            user
            # check that projects is a field and not expanded into a serializer
            and "projects" in self.fields
            and isinstance(self.fields["projects"], ManyRelatedField)
        ):
            self.fields[
                "projects"
            ].child_relation.queryset = Project.objects.get_editable(user)

    def _init_presigned_url(self, request, user, is_document, is_list):
        """Only shown presigned url if needed"""
        is_create = self.instance is None

        is_owner = is_create or (is_document and request and self.instance.user == user)
        has_file_url = (
            not is_list
            and hasattr(self, "initial_data")
            and isinstance(self.initial_data, dict)  # guard against bulk creations
            and self.initial_data.get("file_url")
        )
        has_file = is_document and self.instance.status != Status.nofile
        del_presigned_url = (
            (is_create and has_file_url) or is_list or has_file or not is_owner
        )
        if del_presigned_url and "presigned_url" in self.fields:
            # only show presigned url if we are creating a new document without a
            # file url, or the document has not had a file uploaded yet
            del self.fields["presigned_url"]

    def _init_change_ownership(self, request, user, is_document, is_list):
        """Check for change ownership permissions"""
        perm = "documents.change_ownership_document"
        if not (user and user.is_authenticated):
            return
        if request.method not in ("PUT", "PATCH"):
            # only needed for updates
            return
        if is_document:
            has_perm = user.has_perm(perm, self.instance)
        elif is_list:
            try:
                instances = self.instance.filter(
                    id__in=[d["id"] for d in self.initial_data]
                )[: settings.REST_BULK_LIMIT]
                prefetch_related_objects([user], "organizations")
                has_perm = all(user.has_perm(perm, i) for i in instances)
            except (ValueError, KeyError):
                has_perm = False
        else:
            return
        if has_perm:
            # if this user has change ownership permissions, they may change the
            # user and organization which own this document
            self.fields["user"].read_only = False
            self.fields["user"].queryset = User.objects.filter(
                organizations__in=request.user.organizations.all()
            ).distinct()
            self.fields["organization"].read_only = False
            self.fields["organization"].queryset = request.user.organizations.all()

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

        key_p = re.compile(fr"^{DATA_KEY_REGEX}$")
        if not all(isinstance(k, str) and key_p.match(k) for k in value):
            raise serializers.ValidationError(
                "`data` JSON object must have alphanumeric string keys"
            )

        if not all(isinstance(v, list) for v in value.values()):
            raise serializers.ValidationError(
                "`data` JSON object must have arrays for values of all top level "
                "object properties"
            )

        if not all(isinstance(v, str) for v_ in value.values() for v in v_):
            raise serializers.ValidationError(
                "`data` JSON object must have strings for all values within the lists"
                "of top level object properties"
            )

        if not all(len(v) <= DATA_VALUE_LENGTH for v_ in value.values() for v in v_):
            raise serializers.ValidationError(
                "`data` JSON object must have strings for all values within the lists"
                "of top level object properties"
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
        return storage.presign_url(obj.original_path, "put_object")

    def get_edit_access(self, obj):
        request = self.context.get("request")
        if not request:
            return False
        return request.user.has_perm("documents.change_document", obj)

    def get_canonical_url(self, obj):
        return f"{settings.DOCCLOUD_URL}/documents/{obj.pk}-{obj.slug}"

    def bulk_create_attrs(self, attrs):
        """Set the slug on bulk creation"""
        attrs["slug"] = slugify(attrs["title"])
        return attrs


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
            "content": {"required": False, "max_length": 2000},
            "title": {"max_length": 500},
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
        """Check the coordinates"""
        # if none of the coords are set, this is a page note, no further validating
        if all(attrs.get(attr) is None for attr in ("x1", "x2", "y1", "y2")):
            return attrs

        # if some of the coordinates are set, all must be set
        if any(attrs.get(attr) is None for attr in ("x1", "x2", "y1", "y2")):
            raise serializers.ValidationError(
                "You must set either all of none of the note coordinates"
            )

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
        extra_kwargs = {"title": {"max_length": 200}}

    def validate_page_number(self, value):
        value = super().validate_page_number(value)

        if self.instance and self.instance.page_number == value:
            # if we are updating an existing section, it should not conflict
            # with itself
            return value

        view = self.context.get("view")
        document = Document.objects.get(pk=view.kwargs["document_pk"])
        if document.sections.filter(page_number=value).exists():
            raise serializers.ValidationError(
                "You may not add more than one section to a page"
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


class LegacyEntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = LegacyEntity
        fields = ["kind", "value", "relevance", "occurrences"]


class EntityDateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntityDate
        fields = ["date", "occurrences"]


class DataSerializer(serializers.Serializer):
    # pylint: disable=abstract-method
    values = serializers.ListSerializer(
        child=serializers.CharField(max_length=DATA_VALUE_LENGTH)
    )


class DataAddRemoveSerializer(serializers.Serializer):
    # pylint: disable=abstract-method
    values = serializers.ListSerializer(
        required=False, child=serializers.CharField(max_length=DATA_VALUE_LENGTH)
    )
    remove = serializers.ListSerializer(required=False, child=serializers.CharField())


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


class ModificationSerializer(serializers.Serializer):
    # pylint: disable=abstract-method
    type = serializers.ChoiceField([("rotate", "rotate")])
    angle = serializers.ChoiceField(
        choices=[("cc", "cc"), ("ccw", "ccw"), ("hw", "hw")], required=False
    )

    def validate(self, attrs):
        if attrs["type"] == "rotate" and "angle" not in attrs:
            raise serializers.ValidationError(
                "Angle must be specified for rotation modifications"
            )

        return attrs


class ModificationSpecItemSerializer(serializers.Serializer):
    # pylint: disable=abstract-method
    page = serializers.CharField()
    id = serializers.PrimaryKeyRelatedField(
        required=False, queryset=Document.objects.all()
    )
    slug = serializers.CharField(required=False, read_only=True)
    page_spec = serializers.ListField(required=False, read_only=True)
    page_length = serializers.IntegerField(required=False, read_only=True)
    modifications = ModificationSerializer(required=False, many=True)

    def validate_modifications(self, modifications):
        rotation_count = sum(
            1 for modification in modifications if modification["type"] == "rotate"
        )

        if rotation_count > 1:
            raise serializers.ValidationError(
                "Invalid to specify more than one rotation modification per item"
            )

        return modifications

    # pylint: disable=too-many-locals
    def validate(self, attrs):
        view = self.context.get("view")
        request = self.context.get("request")

        # Use the current document by default, overridden by setting id
        document = attrs.get("id", Document.objects.get(pk=view.kwargs["document_pk"]))
        slug = document.slug

        # Check permissions
        if not request.user.has_perm("documents.view_document", document):
            raise exceptions.PermissionDenied(
                "You may only import pages from documents you can view"
            )

        # Subroutine to ensure page numbers passed in spec match constraints
        def validate_page_number(page_number):
            try:
                page_number = int(page_number)
            except ValueError:
                raise serializers.ValidationError(
                    "Page spec must have integer page numbers"
                )
            if page_number >= document.page_count or page_number < 0:
                raise serializers.ValidationError(
                    f"Must be a valid page for the document {document.pk}: "
                    f"{page_number} (page count: {document.page_count})"
                )
            return page_number

        value = attrs["page"]
        parts = value.split(",")
        result = []
        incremented_pages = []
        page_length = 0
        for part in parts:
            if "-" in part:
                subparts = part.split("-")
                if len(subparts) != 2:
                    raise serializers.ValidationError(
                        f"Page spec has too many parts ({subparts})"
                    )
                page1 = validate_page_number(subparts[0])
                page2 = validate_page_number(subparts[1])
                if page1 >= page2:
                    raise serializers.ValidationError("Page range must be ascending")
                if page1 == page2:
                    # Consolidate to a single page
                    result.append(page1)
                    incremented_pages.append(f"{page1 + 1}")
                    page_length += 1
                else:
                    result.append((page1, page2))
                    incremented_pages.append(f"{page1 + 1}-{page2 + 1}")
                    page_length += page2 - page1 + 1
            else:
                page = validate_page_number(part)
                result.append(page)
                incremented_pages.append(f"{page + 1}")
                page_length += 1

        # Put transformed page spec data into a new attribute
        attrs["page_spec"] = result
        # Increment page ranges for compatibility with pdfium
        attrs["page"] = ",".join(incremented_pages)
        # Store length of page range
        attrs["page_length"] = page_length
        attrs["slug"] = slug
        return attrs


class ModificationSpecSerializer(serializers.Serializer):
    # pylint: disable=abstract-method
    data = ModificationSpecItemSerializer(many=True)


class ProcessDocumentSerializer(serializers.Serializer):
    # pylint: disable=abstract-method

    force_ocr = serializers.BooleanField(
        label=_("Force OCR"), default=False, help_text=_("Force OCR on this document")
    )
    id = serializers.IntegerField(
        label=_("ID"), help_text=_("ID of the document to process")
    )

    def __init__(self, *args, **kwargs):
        bulk = kwargs.pop("bulk", False)
        super().__init__(*args, **kwargs)
        if not bulk:
            # ID field is only for bulk process
            del self.fields["id"]

    class Meta:
        list_serializer_class = BulkListSerializer


class EntitySerializer(serializers.ModelSerializer):
    kind = ChoiceField(EntityKind, help_text=Entity._meta.get_field("kind").help_text)

    class Meta:
        model = Entity
        fields = ["name", "kind", "description", "mid", "wikipedia_url", "metadata"]


class EntityOccurrenceSerializer(serializers.ModelSerializer):
    entity = EntitySerializer()
    occurrences = serializers.SerializerMethodField(
        label=_("Occurrences"),
        help_text=EntityOccurrence._meta.get_field("occurrences").help_text,
    )

    def get_occurrences(self, obj):
        def fix(entity):
            value = entity.pop("kind", 0)
            entity["kind"] = OccurrenceKind.attributes.get(value, value)
            return entity

        return [fix(e) for e in obj.occurrences]

    class Meta:
        model = EntityOccurrence
        fields = ["entity", "relevance", "occurrences"]
