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
from documentcloud.core.pagination import CursorPagination
from documentcloud.documents.choices import Status
from documentcloud.organizations.stats_api.models import OrganizationStats
from documentcloud.organizations.stats_api.serializers import (
    OrganizationStatsSerializer,
)


class OrganizationStatsViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = OrganizationStatsSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [django_filters.DjangoFilterBackend]
    pagination_class = CursorPagination
    lookup_field = "organization__uuid"
    lookup_url_kwarg = "uuid"

    class Filter(django_filters.FilterSet):
        uploaded_within_days = django_filters.NumberFilter(
            method="filter_uploaded_within_days",
            label="Uploaded in last N days",
            help_text=(
                "Return orgs whose most recent upload was within the last N days."
            ),
        )

        def filter_uploaded_within_days(self, queryset, _name, value):
            days = int(value)
            if days < 0:
                return queryset.none()
            cutoff = timezone.now() - timedelta(days=days)
            return queryset.filter(last_upload_at__gte=cutoff)

        class Meta:
            model = OrganizationStats
            fields = []

    filterset_class = Filter

    def get_queryset(self):
        return OrganizationStats.objects.select_related("organization").filter(
            organization__individual=False
        )

    def _annotate_and_prefetch(self, queryset):
        cutoff = timezone.now() - timedelta(days=settings.UPLOAD_WINDOW_DAYS)
        return (
            queryset.select_related("organization", "organization__parent")
            .prefetch_related("organization__groups")
            .annotate(
                total_documents=Count(
                    "organization__documents",
                    filter=~Q(organization__documents__status=Status.deleted),
                    distinct=True,
                ),
                recent_upload_count=Count(
                    "organization__documents",
                    filter=Q(organization__documents__created_at__gte=cutoff)
                    & ~Q(organization__documents__status=Status.deleted),
                    distinct=True,
                ),
            )
        )

    def paginate_queryset(self, queryset):
        page = super().paginate_queryset(queryset)
        annotated = self._annotate_and_prefetch(
            OrganizationStats.objects.filter(pk__in=[o.pk for o in page])
        ).order_by("pk")
        return list(annotated)

    def get_object(self):
        obj = super().get_object()
        return self._annotate_and_prefetch(
            OrganizationStats.objects.filter(pk=obj.pk)
        ).get()

    @action(detail=False, methods=["get"])
    def aged_out(self, request):
        """Orgs with a document that crossed the window boundary since `since`,
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
                organization__documents__created_at__gte=since_dt - win,
                organization__documents__created_at__lt=now - win,
            )
            .distinct()
        )

        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)
