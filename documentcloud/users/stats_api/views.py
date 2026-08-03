# Django
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

# Standard Library
from datetime import timedelta

# Third Party
from django_filters import rest_framework as django_filters

# DocumentCloud
from documentcloud.core.pagination import CursorCountPagination
from documentcloud.documents.choices import Status
from documentcloud.users.stats_api.models import UserStats
from documentcloud.users.stats_api.serializers import UserStatsSerializer


class UserStatsViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = UserStatsSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [django_filters.DjangoFilterBackend]
    pagination_class = CursorCountPagination
    lookup_field = "user__uuid"
    lookup_url_kwarg = "uuid"

    class Filter(django_filters.FilterSet):
        SINCE_FIELDS = ["last_upload_at", "user__last_login"]

        active_within_days = django_filters.NumberFilter(
            method="filter_active_within_days",
            label="Active in last N days (upload or login)",
            help_text="Return users who uploaded or logged in within the last N days.",
        )
        uploaded_within_days = django_filters.NumberFilter(
            method="filter_uploaded_within_days",
            label="Uploaded in last N days",
            help_text="Return users who uploaded a document in the last N days.",
        )
        logged_in_within_days = django_filters.NumberFilter(
            method="filter_logged_in_within_days",
            label="Logged in within last N days",
            help_text=(
                "Return users whose most recent login was within the last N days."
            ),
        )

        def filter_active_within_days(self, queryset, _name, value):
            days = int(value)
            if days < 0:
                return queryset.none()
            cutoff = timezone.now() - timedelta(days=days)
            query = Q()
            for field in self.SINCE_FIELDS:
                query |= Q(**{f"{field}__gt": cutoff})
            return queryset.filter(query)

        def filter_uploaded_within_days(self, queryset, _name, value):
            days = int(value)
            if days < 0:
                return queryset.none()
            cutoff = timezone.now() - timedelta(days=days)
            return queryset.filter(last_upload_at__gte=cutoff)

        def filter_logged_in_within_days(self, queryset, _name, value):
            days = int(value)
            if days < 0:
                return queryset.none()
            cutoff = timezone.now() - timedelta(days=days)
            return queryset.filter(user__last_login__gte=cutoff)

        class Meta:
            model = UserStats
            fields = []

    filterset_class = Filter

    def get_queryset(self):
        cutoff = timezone.now() - timedelta(days=settings.UPLOAD_WINDOW_DAYS)
        return UserStats.objects.select_related("user").annotate(
            total_documents=Count(
                "user__documents",
                filter=~Q(user__documents__status=Status.deleted),
                distinct=True,
            ),
            recent_upload_count=Count(
                "user__documents",
                filter=Q(user__documents__created_at__gte=cutoff)
                & ~Q(user__documents__status=Status.deleted),
                distinct=True,
            ),
        )

    @action(detail=False, methods=["get"])
    def aged_out(self, request):
        """Users with a document that crossed the window boundary since `since`,
        so their upload count has dropped and needs re-syncing."""
        since = request.query_params.get("since")
        if not since:
            return Response({"error": "since query param is required"}, status=400)
        since_dt = parse_datetime(since)
        if since_dt is None:
            return Response({"error": "since must be an ISO 8601 datetime"}, status=400)

        win = timedelta(days=settings.UPLOAD_WINDOW_DAYS)
        now = timezone.now()
        qs = (
            self.get_queryset()
            .filter(
                user__documents__created_at__gte=since_dt - win,
                user__documents__created_at__lt=now - win,
            )
            .distinct()
        )

        page = self.paginate_queryset(qs)
        return Response(self.get_serializer(page, many=True).data)
