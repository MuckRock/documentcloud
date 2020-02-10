# Django
from django.utils.translation import ugettext_lazy as _
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

    def validate_document(self, value):
        view = self.context.get("view")
        project = Project.objects.get(pk=view.kwargs["project_pk"])
        if project.documents.filter(pk=value.pk).exists():
            raise serializers.ValidationError(
                f"You may not add document {value.pk} to this project more than once"
            )
        return value

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
    email = serializers.SlugRelatedField(
        label=_("Email"),
        source="user",
        slug_field="email",
        write_only=True,
        queryset=User.objects.all(),
        help_text=_("The email address of the user you wish to add as a collaborator"),
    )

    class Meta:
        model = Collaboration
        fields = ["user", "email"]
        extra_kwargs = {"user": {"read_only": True}}

    def validate_email(self, value):
        view = self.context.get("view")
        project = Project.objects.get(pk=view.kwargs["project_pk"])
        if project.collaborators.filter(email=value.email).exists():
            raise serializers.ValidationError(
                f"You may not add user {value.email} as a collaborator more than once"
            )
        return value
