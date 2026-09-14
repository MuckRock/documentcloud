# Django
from django.conf import settings
from django.db.models import Exists, OuterRef, Prefetch, Q
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
from documentcloud.organizations.models import Organization
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
    pagination_class = CursorPagination
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
        used_ai_credits_within_days = django_filters.NumberFilter(
            method="filter_used_ai_credits_within_days",
            label="Used AI credits within last N days",
            help_text="Return users who used AI credits within the last N days.",
        )

        def filter_active_within_days(self, queryset, _name, value):
            days = int(value)
            if days < 0:
                return queryset.none()
            cutoff = timezone.now() - timedelta(days=days)
            query = Q()
            for field in self.SINCE_FIELDS:
                query |= Q(**{f"{field}__gte": cutoff})
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

        def filter_used_ai_credits_within_days(self, queryset, _name, value):
            days = int(value)
            if days < 0:
                return queryset.none()
            cutoff = timezone.now() - timedelta(days=days)
            return queryset.filter(last_ai_credit_at__gte=cutoff)

        class Meta:
            model = UserStats
            fields = []

    filterset_class = Filter

    def get_queryset(self):
        return UserStats.objects.select_related("user").prefetch_related(
            Prefetch(
                "user__organizations",
                queryset=Organization.objects.filter(individual=True),
                to_attr="individual_orgs",
            )
        )

    @action(detail=False, methods=["get"])
    def aged_out(self, request):
        """Users with a document that crossed the recent-upload window boundary
        since `since`, so their recent_upload_count has dropped without any event.
        Lets the caller (Squarelet) know which users to re-sync.
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

        # Documents that left the recent window since `since`. Exists() short-circuits
        # per user instead of joining + distinct over a heavy user's whole document
        # set (which can time out).
        aged_doc = Document.objects.filter(
            user_id=OuterRef("user_id"),
            created_at__gte=since_dt - win,
            created_at__lt=now - win,
        )
        qs = self.get_queryset().filter(Exists(aged_doc))

        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)
