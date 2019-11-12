# Django
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers

# Third Party
from django_redis import get_redis_connection
from redis.exceptions import RedisError
from rest_flex_fields import FlexFieldsModelSerializer

# DocumentCloud
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
from documentcloud.environment.environment import storage, RedisFields
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

    texts_remaining = serializers.SerializerMethodField(
        label=_("Text pages remaining"),
        read_only=True,
        help_text=_(
            "How many pages are left to be OCRed - only present during processing"
        ),
    )
    images_remaining = serializers.SerializerMethodField(
        label=_("Image pages remaining"),
        read_only=True,
        help_text=_(
            "How many pages are left to have their image extracted via pdfium - "
            "only present during processing"
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
            "images_remaining",
            "language",
            "organization",
            "page_count",
            "page_spec",
            "presigned_url",
            "slug",
            "source",
            "status",
            "texts_remaining",
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

        self._redis_data = None
        if not isinstance(self.instance, Document) or self.instance.status not in (
            Status.pending,
            Status.readable,
        ):
            # images and texts remaining fields or for processing documents only
            del self.fields["images_remaining"]
            del self.fields["texts_remaining"]

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
        return storage.presign_url(obj.pdf_path, "put_object")

    def get_images_remaining(self, obj):
        """Get the images remaining from the processing redis instance"""
        if self._redis_data is None:
            self._get_redis(obj)
        return self._redis_data[0]

    def get_texts_remaining(self, obj):
        """Get the texts remaining from the processing redis instance"""
        if self._redis_data is None:
            self._get_redis(obj)
        return self._redis_data[1]

    def _get_redis(self, obj):
        """Get a value from the processing redis instance"""
        redis = get_redis_connection("processing")
        try:
            with redis.pipeline() as pipeline:
                pipeline.get(RedisFields.images_remaining(obj.pk)).get(
                    RedisFields.texts_remaining(obj.pk)
                )
                self._redis_data = pipeline.execute()
        except RedisError:
            self._redis_data = (None, None)


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
