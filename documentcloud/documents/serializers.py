# Django
from rest_framework import serializers

# DocumentCloud
from documentcloud.core.choices import Language
from documentcloud.documents.choices import Access
from documentcloud.documents.models import Document


class DocumentSerializer(serializers.ModelSerializer):

    file = serializers.FileField(write_only=True, required=False)
    file_url = serializers.URLField(write_only=True, required=False)

    class Meta:
        model = Document
        fields = [
            "access",
            "created_at",
            "description",
            "file",
            "file_url",
            "id",
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
            "user": {"read_only": True},
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
