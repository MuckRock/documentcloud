# Django
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# Third Party
# Third party
from drf_spectacular.utils import extend_schema_field

# DocumentCloud
from documentcloud.organizations.models import Organization


class OrganizationSerializer(serializers.ModelSerializer):

    plan = serializers.SerializerMethodField(
        label=_("Plan"),
        help_text=(
            "The name of the plan this organization is subscribed to. "
            "Only viewable by organization members."
        ),
    )
    monthly_credits = serializers.SerializerMethodField(
        label=_("Monthly Credits"),
        read_only=True,
        help_text=(
            "Number of monthly premium credits this organization has left. "
            "This will reset to monthly_credit_allowance on credit_reset_date. "
            "This includes shared credits from parents and groups. "
            "Only viewable be organization members."
        ),
    )
    purchased_credits = serializers.SerializerMethodField(
        label=_("Purchased Credits"),
        read_only=True,
        help_text=(
            "Number of purchased premium credits. "
            "These do not reset or expire. "
            "This includes shared credits from parents and groups. "
            "Only viewable by organization members."
        ),
    )
    credit_reset_date = serializers.DateField(
        source="date_update",
        read_only=True,
        help_text=(
            "The date that monthly_credits reset. "
            "Only viewable by organization members."
        ),
    )
    monthly_credit_allowance = serializers.SerializerMethodField(
        read_only=True,
        help_text=(
            "The amount of credits that monthly_credits will reset to. "
            "Only viewable by organization members."
        ),
    )

    class Meta:
        model = Organization
        fields = [
            "id",
            "avatar_url",
            "individual",
            "name",
            "slug",
            "uuid",
            "monthly_credits",
            "purchased_credits",
            "credit_reset_date",
            "monthly_credit_allowance",
            "plan",
        ]
        extra_kwargs = {
            "avatar_url": {"read_only": True},
            "individual": {"read_only": True},
            "name": {"read_only": True},
            "slug": {"read_only": True},
        }

    def to_representation(self, instance):
        """Check if this instance should display AI credits"""
        if "monthly_credits" in self.fields:
            # skip checks if we have already removed the fields
            request = self.context and self.context.get("request")
            user = request and request.user
            is_org = isinstance(instance, Organization)
            if not (
                is_org and user and user.is_authenticated and instance.has_member(user)
            ):
                # only members may see AI credit information
                self.fields.pop("monthly_credits")
                self.fields.pop("purchased_credits")
                self.fields.pop("credit_reset_date")
                self.fields.pop("monthly_credit_allowance")
                self.fields.pop("plan")

        return super().to_representation(instance)

    @extend_schema_field(serializers.CharField())
    def get_plan(self, obj):
        if obj.entitlement:
            return obj.entitlement.name
        else:
            return "Free"

    def get_monthly_credits(self, obj):
        return obj.get_total_monthly_ai_credits()

    def get_purchased_credits(self, obj):
        return obj.get_total_number_ai_credits()

    def get_monthly_credit_allowance(self, obj):
        return obj.get_total_monthly_ai_credits_allowance()


class AICreditSerializer(serializers.Serializer):
    """Serializer for the AI credit endpoint"""

    # pylint: disable=abstract-method

    ai_credits = serializers.IntegerField(
        label=_("AI Credits"),
        help_text=_("Amount of AI credits to charge to the organization"),
    )
    note = serializers.CharField(
        label=_("Note"),
        help_text=_("What are these credits being used for?"),
        max_length=1000,
        required=False,
    )
    user_id = serializers.IntegerField(label=_("User ID"), required=False)
    addonrun_id = serializers.UUIDField(label=_("AddOn Run ID"), required=False)

    def validate_ai_credits(self, value):
        if value < 0:
            raise serializers.ValidationError("AI credits may not be negative")
        return value
