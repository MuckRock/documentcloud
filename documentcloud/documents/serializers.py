# Django
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers

# DocumentCloud
from documentcloud.core.choices import Language
from documentcloud.documents.choices import Access
from documentcloud.documents.models import Document, Note


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

    class Meta:
        model = Document
        fields = [
            "id",
            "access",
            "created_at",
            "description",
            "file",
            "file_url",
            "language",
            "organization",
            "page_count",
            "slug",
            "source",
            "status",
            "title",
            "updated_at",
            "user",
        ]
        extra_kwargs = {
            "access": {"default": Access.private},
            "created_at": {"read_only": True},
            "description": {"required": False},
            "language": {"default": Language.english},
            "organization": {"read_only": True},
            "page_count": {"read_only": True},
            "slug": {"read_only": True},
            "source": {"required": False},
            "status": {"read_only": True},
            "updated_at": {"read_only": True},
            "user": {"read_only": True, "style": {"base_template": "input.html"}},
        }

    def validate(self, attrs):
        if self.partial:
            return attrs
        if "file" not in attrs and "file_url" not in attrs:
            raise serializers.ValidationError(
                "You must pass in either file or file_url"
            )
        if "file" in attrs and "file_url" in attrs:
            raise serializers.ValidationError(
                "You must not pass in both file and file_url"
            )
        return attrs


class NoteSerializer(serializers.ModelSerializer):
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
            "access": {"default": Access.private},
            "created_at": {"read_only": True},
            "organization": {"read_only": True},
            "updated_at": {"read_only": True},
            "user": {"read_only": True, "style": {"base_template": "input.html"}},
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
