# Django
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# Third Party
from drf_spectacular.utils import extend_schema_field
from rest_flex_fields.serializers import FlexFieldsModelSerializer

# DocumentCloud
from documentcloud.organizations.models import Organization
from documentcloud.users.models import User


class UserSerializer(FlexFieldsModelSerializer):
    organization = serializers.IntegerField(
        source="organization.pk",
        label=_("Active Organization"),
        help_text=(
            "This is the user's current organization - it must be set to one of the "
            "organiations they are a member of"
        ),
    )
    verified_journalist = serializers.SerializerMethodField(
        source="verified_organizations",
        help_text=("Whether the user is a verified journalist or not"),
    )
    admin_organizations = serializers.SerializerMethodField(
        source="admin_organizations",
        help_text=("List of organizations the user is an admin for"),
    )

    class Meta:
        model = User
        fields = [
            "id",
            "avatar_url",
            "feature_level",
            "is_staff",
            "name",
            "organization",
            "organizations",
            "admin_organizations",
            "username",
            "uuid",
            "verified_journalist",
            "email",
        ]
        extra_kwargs = {
            "avatar_url": {"read_only": True},
            "name": {"read_only": True},
            "organizations": {
                "read_only": True,
                "help_text": "A list of the IDs of the organizations this user belongs to.",
            },
            "username": {"read_only": True},
            "email": {"read_only": True},
        }

        expandable_fields = {
            "organization": ("documentcloud.organizations.OrganizationSerializer", {})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        context = kwargs.get("context", {})
        request = context.get("request")
        view = context.get("view")
        if not (request and request.user.is_staff):
            self.fields.pop("is_staff")
        if not view or view.kwargs.get("pk") != "me":
            self.fields.pop("feature_level")
            self.fields.pop("email")

    def validate_organization(self, value):
        organization = Organization.objects.filter(pk=value).first()
        if not organization:
            raise serializers.ValidationError(f"Organization `{value}` does not exist")
        return organization

    def update(self, instance, validated_data):
        try:
            instance.organization = validated_data["organization"]["pk"]
        except ValueError as exc:
            raise serializers.ValidationError(exc.args[0])
        return instance

    def get_verified_journalist(self, obj):
        """Is this user a member of a verified journalist organization?"""
        # If doing a list of users, we preload the verified organizations
        # in order to avoid n+1 queries.  If the preloaded organizations are not
        # present, use the property on user to make the query
        if hasattr(obj, "verified_organizations"):
            return bool(obj.verified_organizations)
        else:
            return obj.verified_journalist

    @extend_schema_field(serializers.ListField(child=serializers.IntegerField()))
    def get_admin_organizations(self, obj):
        """The organizations this user is an admin of"""
        # If doing a list of users, we preload the admin organizations
        # in order to avoid n+1 queries.
        if hasattr(obj, "admin_organizations"):
            return [o.pk for o in obj.admin_organizations]
        else:
            return [o.pk for o in obj.organizations.filter(memberships__admin=True)]


class MessageSerializer(serializers.Serializer):
    """A serializer for sending yourself a message"""

    # pylint: disable=abstract-method

    subject = serializers.CharField(max_length=255)
    content = serializers.CharField()
