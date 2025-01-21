# Django
from rest_framework import serializers

# DocumentCloud
from documentcloud.statistics.models import Statistics


class StatisticsSerializer(serializers.ModelSerializer):
    """Serializer for DocumentCloud Statistics"""

    class Meta:
        model = Statistics
        fields = "__all__"
