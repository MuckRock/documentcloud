# Django
from rest_framework import serializers

# DocumentCloud
from documentcloud.organizations.models import Organization
from documentcloud.users.models import User


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "avatar_url", "individual", "name", "slug", "uuid"]
        extra_kwargs = {
            "avatar_url": {"read_only": True},
            "individual": {"read_only": True},
            "name": {"read_only": True},
            "slug": {"read_only": True},
        }
