# Django
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions, serializers

# Third Party
from rest_flex_fields.serializers import FlexFieldsModelSerializer

# DocumentCloud
from documentcloud.documents.fields import ChoiceField
from documentcloud.documents.models import Document
from documentcloud.drf_bulk.serializers import BulkListSerializer
from documentcloud.projects.choices import CollaboratorAccess
from documentcloud.projects.models import Collaboration, Project, ProjectMembership
from documentcloud.users.models import User


class ProjectSerializer(serializers.ModelSerializer):
    edit_access = serializers.SerializerMethodField(
        label=_("Edit Access"),
        read_only=True,
        help_text=_("Does the current user have edit access to this project"),
    )
    add_remove_access = serializers.SerializerMethodField(
        label=_("Add/Remove Access"),
        read_only=True,
        help_text=_(
            "Does the current user have permissions to add and remove documents "
            "to this project"
        ),
    )

    class Meta:
        model = Project
        fields = [
            "id",
            "created_at",
            "description",
            "edit_access",
            "add_remove_access",
            "private",
            "slug",
            "title",
            "updated_at",
            "user",
        ]
        extra_kwargs = {
            "created_at": {"read_only": True},
            "description": {"required": False, "max_length": 1000},
            "private": {"required": False},
            "slug": {"read_only": True},
            "updated_at": {"read_only": True},
            "user": {"read_only": True},
        }

    def get_edit_access(self, obj):
        request = self.context.get("request")
        if not request:
            return False
        # check if we have precomputed is_admin for performance reasons
        if hasattr(obj, "is_admin"):
            return obj.is_admin
        else:
            return request.user.has_perm("projects.change_project", obj)

    def get_add_remove_access(self, obj):
        request = self.context.get("request")
        if not request:
            return False
        # check if we have precomputed is_editor for performance reasons
        if hasattr(obj, "is_editor"):
            return obj.is_editor
        else:
            return request.user.has_perm("projects.add_remove_project", obj)


class ProjectMembershipSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = ProjectMembership
        list_serializer_class = BulkListSerializer
        update_lookup_field = "document"
        fields = ["document", "edit_access"]
        extra_kwargs = {
            "document": {
                "queryset": Document.objects.none(),
                "style": {"base_template": "input.html"},
            },
            "edit_access": {"default": None},
        }
        expandable_fields = {
            "document": ("documentcloud.documents.DocumentSerializer", {})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        view = self.context.get("view")
        if request and request.user and "document" in self.fields:
            self.fields["document"].queryset = Document.objects.get_viewable(
                request.user
            )
        if view and "document_id" in view.kwargs and "document" in self.fields:
            self.fields["document"].required = False

    def validate_document(self, value):
        if (
            # if bulk update, will be a query set, we do not need to validate
            # if creation, will be None, do not need to validate
            isinstance(self.instance, ProjectMembership)
            and self.instance.document != value
        ):
            raise serializers.ValidationError("You may not update `document`")

        view = self.context.get("view")
        project = Project.objects.get(pk=view.kwargs["project_pk"])
        if not self.instance and project.documents.filter(pk=value.pk).exists():
            raise serializers.ValidationError(
                f"You may not add document {value.pk} to this project more than once"
            )

        return value

    def validate(self, attrs):
        request = self.context.get("request")
        if isinstance(self.instance, ProjectMembership):
            document = self.instance.document
        else:
            document = attrs["document"]

        edit_access = attrs.get("edit_access")
        can_share = request.user.has_perm("documents.share_document", document)
        # if edit access is not set, default to sharing if you have permission to
        if edit_access is None:
            attrs["edit_access"] = can_share
        # if explicitly set to true, check permissions
        elif edit_access is True and not can_share:
            raise exceptions.PermissionDenied(
                "You may only set `edit_access` to true if you have permission "
                "to share `document`"
            )
        return attrs


class CollaborationSerializer(FlexFieldsModelSerializer):
    email = serializers.SlugRelatedField(
        label=_("Email"),
        source="user",
        slug_field="email",
        write_only=True,
        queryset=User.objects.all(),
        help_text=_("The email address of the user you wish to add as a collaborator"),
        error_messages={
            **serializers.SlugRelatedField.default_error_messages,
            "does_not_exist": _(
                "No user with the {slug_name} {value} was found. Please check the "
                "email, or ask the user to "
                f'<a href="{settings.SQUARELET_URL}/accounts/signup/'
                '?intent=documentcloud">first register for a free account here</a> '
                "and then log in to DocumentCloud once, and then this error should "
                "resolve."
            ),
        },
    )
    access = ChoiceField(
        CollaboratorAccess,
        default=CollaboratorAccess.view,
        help_text=Collaboration._meta.get_field("access").help_text,
    )

    class Meta:
        model = Collaboration
        fields = ["user", "email", "access"]
        extra_kwargs = {"user": {"read_only": True}}
        expandable_fields = {"user": ("documentcloud.users.UserSerializer", {})}

    def validate_access(self, value):
        """Disallow demoting the last admin"""
        view = self.context.get("view")
        project = Project.objects.get(pk=view.kwargs["project_pk"])
        admins = project.collaborators.filter(
            collaboration__access=CollaboratorAccess.admin
        )
        if (
            self.instance
            and value != CollaboratorAccess.admin
            and len(admins) == 1
            and self.instance.user in admins
        ):
            raise serializers.ValidationError(
                "You may not demote the only admin in a project"
            )

        return value

    def validate_email(self, value):
        view = self.context.get("view")
        project = Project.objects.get(pk=view.kwargs["project_pk"])

        # on updates check that email does not change
        if self.instance and self.instance.user != value:
            raise serializers.ValidationError("You may not update `email`")

        # check for duplicates on creation (instance is none implies creation)
        if (
            not self.instance
            and project.collaborators.filter(email=value.email).exists()
        ):
            raise serializers.ValidationError(
                f"You may not add user {value.email} as a collaborator more than once"
            )
        return value
