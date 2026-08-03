# Django
from django.utils import timezone
from rest_framework import serializers

# DocumentCloud
from documentcloud.users.stats_api.models import UserStats


class UserStatsSerializer(serializers.ModelSerializer):
    uuid = serializers.UUIDField(source="user.uuid", read_only=True)
    total_documents = serializers.IntegerField(read_only=True)
    days_since_last_upload = serializers.SerializerMethodField(
        help_text="Number of days since the last time the user uploaded a document"
    )
    last_login_at = serializers.DateTimeField(source="user.last_login", read_only=True)
    recent_upload_count = serializers.SerializerMethodField(
        help_text="Number of documents uploaded within the configured recent window "
        "(UPLOAD_WINDOW_DAYS, currently defaults to 90)."
    )

    class Meta:
        model = UserStats
        fields = [
            "uuid",
            "total_documents",
            "last_upload_at",
            "days_since_last_upload",
            "last_login_at",
            "recent_upload_count",
        ]
        read_only_fields = fields

    def get_days_since_last_upload(self, obj):
        if obj.last_upload_at is None:
            return None
        return (timezone.now() - obj.last_upload_at).days

    def get_recent_upload_count(self, obj):
        return getattr(obj, "recent_upload_count", None)
