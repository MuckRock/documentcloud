# Django
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers

# Third Party
import furl
import redis

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


class DocumentSerializer(serializers.ModelSerializer):

    file = serializers.FileField(
        label=_("File"),
        write_only=True,
        required=False,
        help_text=_("The file to upload - use this field or `file_url`"),
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
            "created_at",
            "description",
            "file",
            "file_url",
            "images_remaining",
            "language",
            "organization",
            "page_count",
            "page_spec",
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
            del self.fields["images_remaining"]
            del self.fields["texts_remaining"]

    def _authenticate_processing(self, request):
        """Check the requests Authorization header for our special token"""
        if not request or not hasattr(request, "auth") or request.auth is None:
            return False

        return "processing" in request.auth["permissions"]

    def validate(self, attrs):
        if self.instance:
            if "file" in attrs:
                raise serializers.ValidationError("You may not update `file`")
            if "file_url" in attrs:
                raise serializers.ValidationError("You may not update `file_url`")
        else:
            if "file" not in attrs and "file_url" not in attrs:
                raise serializers.ValidationError(
                    "You must pass in either `file` or `file_url`"
                )
            if "file" in attrs and "file_url" in attrs:
                raise serializers.ValidationError(
                    "You must not pass in both `file` and `file_url`"
                )
        return attrs

    def get_texts_remaining(self, obj):
        """Get the texts remaining from the processing redis instance"""
        texts_remaining = self._get_redis(obj, "text")
        if texts_remaining is None: return None
        return int(texts_remaining)

    def get_images_remaining(self, obj):
        """Get the images remaining from the processing redis instance"""
        images_remaining = self._get_redis(obj, "image")
        if images_remaining is None: return None
        return int(images_remaining)

    def _get_redis(self, obj, key):
        """Get a value from the processing redis instance"""
        redis_url = furl.furl(settings.REDIS_PROCESSING_URL)
        redis_ = redis.Redis(host=redis_url.host, port=redis_url.port)
        return redis_.hget(obj.pk, key)


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
