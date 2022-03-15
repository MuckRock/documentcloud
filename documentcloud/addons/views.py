# Django
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# Standard Library
from functools import lru_cache

# Third Party
from django_filters import rest_framework as django_filters
from rest_flex_fields import FlexFieldsModelViewSet
from rest_flex_fields.utils import is_expanded

# DocumentCloud
from documentcloud.addons.models import AddOn, AddOnRun
from documentcloud.addons.serializers import AddOnRunSerializer, AddOnSerializer
from documentcloud.addons.tasks import dispatch, update_config


class AddOnViewSet(viewsets.ModelViewSet):
    serializer_class = AddOnSerializer
    queryset = AddOn.objects.none()

    def get_queryset(self):
        return AddOn.objects.get_viewable(self.request.user).order_by("-pk")

    def perform_create(self, serializer):
        """Specify the user and organization"""
        serializer.save(
            user=self.request.user, organization=self.request.user.organization
        )

    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def update_config(self, request):
        name = request.data.get("repository")
        if name:
            update_config.delay(name)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AddOnRunViewSet(FlexFieldsModelViewSet):
    serializer_class = AddOnRunSerializer
    queryset = AddOnRun.objects.none()
    lookup_field = "uuid"
    permit_list_expands = ["addon"]

    @lru_cache()
    def get_queryset(self):
        """Only fetch add-on runs viewable to this user"""
        queryset = AddOnRun.objects.get_viewable(self.request.user).order_by("-pk")
        if is_expanded(self.request, "addon"):
            queryset = queryset.select_related("addon")
        return queryset

    def perform_create(self, serializer):
        with transaction.atomic():
            run = serializer.save(user=self.request.user)
            transaction.on_commit(
                lambda: dispatch.delay(
                    run.addon_id,
                    run.uuid,
                    self.request.user.pk,
                    self.request.data.get("documents"),
                    self.request.data.get("query"),
                    self.request.data["parameters"],
                )
            )

    class Filter(django_filters.FilterSet):
        class Meta:
            model = AddOnRun
            fields = {"dismissed": ["exact"]}

    filterset_class = Filter
