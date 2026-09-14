# Django
from django.conf import settings
from django.db.models import Exists, OuterRef
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
from documentcloud.documents.models import Document
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
        return (
            OrganizationStats.objects.select_related(
                "organization", "organization__parent"
            )
            .prefetch_related("organization__groups")
            .filter(organization__individual=False)
        )

    @action(detail=False, methods=["get"])
    def aged_out(self, request):
        """Orgs with a document that crossed the recent-upload window boundary
        since `since`, so their recent_upload_count has dropped without any event.
        Lets the caller (Squarelet) know which orgs to re-sync.
        """
        since = request.query_params.get("since")
        if not since:
            return Response({"error": "since query param is required"}, status=400)
        since_dt = parse_datetime(since)
        if since_dt is None:
            return Response({"error": "since must be an ISO 8601 datetime"}, status=400)
        if timezone.is_naive(since_dt):
            since_dt = timezone.make_aware(since_dt, timezone.utc)

        win = timedelta(days=settings.UPLOAD_WINDOW_DAYS)
        now = timezone.now()

        # Exists() short-circuits per org instead of joining + distinct over a
        # heavy org's whole document set which can time out.
        aged_doc = Document.objects.filter(
            organization_id=OuterRef("organization_id"),
            created_at__gte=since_dt - win,
            created_at__lt=now - win,
        )
        qs = self.get_queryset().filter(Exists(aged_doc))

        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)
