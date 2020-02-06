# Django
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers

# Third Party
from rest_flex_fields.serializers import FlexFieldsModelSerializer

# DocumentCloud
from documentcloud.organizations.models import Organization
from documentcloud.organizations.serializers import OrganizationSerializer
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

    class Meta:
        model = User
        fields = [
            "id",
            "avatar_url",
            "name",
            "organization",
            "organizations",
            "username",
            "uuid",
        ]
        extra_kwargs = {
            "avatar_url": {"read_only": True},
            "name": {"read_only": True},
            "organizations": {"read_only": True},
            "username": {"read_only": True},
        }
        expandable_fields = {
            "organization": (OrganizationSerializer, {"source": "organization"})
        }

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
