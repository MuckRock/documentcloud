# Django
from django.utils import timezone
from rest_framework import serializers

# DocumentCloud
from documentcloud.organizations.stats_api.models import OrganizationStats


class OrganizationStatsSerializer(serializers.ModelSerializer):
    uuid = serializers.UUIDField(source="organization.uuid", read_only=True)
    total_documents = serializers.IntegerField(read_only=True)
    days_since_last_upload = serializers.SerializerMethodField()
    recent_upload_count = serializers.IntegerField(
        read_only=True,
        help_text="Number of documents uploaded within the configured recent window "
        "(UPLOAD_WINDOW_DAYS, currently defaults to 90).",
    )
    ai_credits = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationStats
        fields = [
            "uuid",
            "total_documents",
            "last_upload_at",
            "days_since_last_upload",
            "recent_upload_count",
            "ai_credits",
            "last_ai_credit_at",
        ]
        read_only_fields = fields

    def get_days_since_last_upload(self, obj):
        if obj.last_upload_at is None:
            return None
        return (timezone.now() - obj.last_upload_at).days

    def get_ai_credits(self, obj):
        org = obj.organization
        return {
            "ai_credits_per_month": org.get_total_monthly_ai_credits_allowance(),
            "monthly_ai_credits": org.get_total_monthly_ai_credits(),
            "number_ai_credits": org.get_total_number_ai_credits(),
        }
