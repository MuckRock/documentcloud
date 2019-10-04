# Django
from rest_framework import serializers

# DocumentCloud
from documentcloud.documents.models import Document
from documentcloud.projects.models import Collaboration, Project, ProjectMembership
from documentcloud.users.models import User


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = [
            "id",
            "created_at",
            "description",
            "private",
            "slug",
            "title",
            "updated_at",
            "user",
        ]
        extra_kwargs = {
            "created_at": {"read_only": True},
            "description": {"required": False},
            "private": {"required": False},
            "slug": {"read_only": True},
            "updated_at": {"read_only": True},
            "user": {"read_only": True},
        }


class ProjectMembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMembership
        fields = ["document", "edit_access"]
        extra_kwargs = {
            "document": {"queryset": Document.objects.none()},
            "edit_access": {"default": False},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user:
            self.fields["document"].queryset = Document.objects.get_viewable(
                request.user
            )

    def update(self, instance, validated_data):
        if validated_data.get("document", instance.document) != instance.document:
            raise serializers.ValidationError("You may not update `document`")
        return super().update(instance, validated_data)

    def validate(self, attrs):
        request = self.context.get("request")
        if self.instance:
            document = self.instance.document
        else:
            document = attrs["document"]
        if attrs.get("edit_access") and not request.user.has_perm(
            "documents.change_document", document
        ):
            raise serializers.ValidationError(
                "You may only set `edit_access` to true if you have permission "
                "to edit `document`"
            )
        return attrs


class CollaborationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collaboration
        fields = ["user"]
        extra_kwargs = {"user": {"queryset": User.objects.none()}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user:
            self.fields["user"].queryset = User.objects.get_viewable(request.user)
