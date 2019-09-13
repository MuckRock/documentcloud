# Django
from rest_framework import serializers

# DocumentCloud
from documentcloud.organizations.models import Organization
from documentcloud.users.models import User


class UserSerializer(serializers.ModelSerializer):
    organization = serializers.IntegerField(source="organization.pk")

    class Meta:
        model = User
        fields = [
            "id",
            "avatar_url",
            "email",
            "name",
            "organization",
            "organizations",
            "username",
            "uuid",
        ]
        extra_kwargs = {
            "avatar_url": {"read_only": True},
            "email": {"read_only": True},
            "name": {"read_only": True},
            "organizations": {"read_only": True},
            "username": {"read_only": True},
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
