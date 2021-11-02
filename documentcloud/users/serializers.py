# Django
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# Third Party
from rest_flex_fields.serializers import FlexFieldsModelSerializer

# DocumentCloud
from documentcloud.organizations.models import Organization
from documentcloud.users.models import User


class UserSerializer(FlexFieldsModelSerializer):
    organization = serializers.IntegerField(
        source="organization.pk",
        label=_("Active Organization"),
        help_text=_(
            "This is the user's current organization - it must be set to one of the "
            "organiations they are a member of"
        ),
    )
    verified_journalist = serializers.SerializerMethodField(
        source="verified_organizations"
    )

    class Meta:
        model = User
        fields = [
            "id",
            "avatar_url",
            "is_staff",
            "name",
            "organization",
            "organizations",
            "username",
            "uuid",
            "verified_journalist",
        ]
        extra_kwargs = {
            "avatar_url": {"read_only": True},
            "name": {"read_only": True},
            "organizations": {"read_only": True},
            "username": {"read_only": True},
        }
        expandable_fields = {
            "organization": ("documentcloud.organizations.OrganizationSerializer", {})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        context = kwargs.get("context", {})
        request = context.get("request")
        if not (request and request.user.is_staff):
            self.fields.pop("is_staff")

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
