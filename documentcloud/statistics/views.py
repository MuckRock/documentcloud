# Django
from rest_framework import mixins, permissions, viewsets

# DocumentCloud
from documentcloud.statistics.models import Statistics
from documentcloud.statistics.serializers import StatisticsSerializer


class StatisticsViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):

    serializer_class = StatisticsSerializer
    queryset = Statistics.objects.all()
    filterset_fields = ("date",)
    permission_classes = [permissions.IsAdminUser]
