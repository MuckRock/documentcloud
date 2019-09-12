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
            "id",
            "user",
            "organization",
            "access",
            "status",
            "title",
            "slug",
            "language",
            "source",
            "description",
            "created_at",
            "updated_at",
            "file",
            "file_url",
        ]
        extra_kwargs = {
            "user": {"read_only": True},
            "organization": {"read_only": True},
            "access": {"default": Access.private},
            "status": {"read_only": True},
            "slug": {"read_only": True},
            "language": {"default": Language.english},
            "source": {"required": False},
            "description": {"required": False},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
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
