# Django
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# DocumentCloud
from documentcloud.organizations.models import Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            "id",
            "avatar_url",
            "individual",
            "monthly_ai_credits",
            "name",
            "number_ai_credits",
            "slug",
            "uuid",
        ]
        extra_kwargs = {
            "avatar_url": {"read_only": True},
            "individual": {"read_only": True},
            "name": {"read_only": True},
            "slug": {"read_only": True},
        }

    def to_representation(self, instance):
        request = self.context and self.context.get("request")
        user = request and request.user
        is_org = isinstance(instance, Organization)
        if not (
            is_org and user and user.is_authenticated and instance.has_member(user)
        ):
            # only members may see AI credits
            self.fields.pop("monthly_ai_credits", None)
            self.fields.pop("number_ai_credits", None)
        return super().to_representation(instance)


class AICreditSerializer(serializers.Serializer):
    """Serializer for the AI credit endpoint"""

    # pylint: disable=abstract-method

    ai_credits = serializers.IntegerField(
        label=_("AI Credits"),
        help_text=_("Amount of AI credits to charge to the organization"),
    )

    def validate_ai_credits(self, value):
        if value < 0:
            raise serializers.ValidationError("AI credits may not be negative")
        return value
