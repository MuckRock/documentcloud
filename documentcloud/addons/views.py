# Django
from django.db import transaction
from django.db.models.expressions import Exists, OuterRef
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
        return (
            AddOn.objects.get_viewable(self.request.user)
            .order_by("-pk")
            .annotate(
                active=Exists(self.request.user.active_addons.filter(pk=OuterRef("pk")))
            )
        )

    def perform_update(self, serializer):
        super().perform_update(serializer)
        # add or remove to add-on from the current user's active add-ons
        # if needed
        if "active_w" not in serializer.validated_data:
            return
        addon = self.get_object()
        if serializer.validated_data["active_w"] and not addon.active:
            self.request.user.active_addons.add(addon)
        if not serializer.validated_data["active_w"] and addon.active:
            self.request.user.active_addons.remove(addon)
        # pylint: disable=pointless-statement, protected-access
        # data is a property, we call it here to populate _data
        serializer.data
        # we need to set _data directly to set the update value from active_w
        serializer._data["active"] = serializer.validated_data["active_w"]

    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def update_config(self, request):
        name = request.data.get("repository")
        if name:
            update_config.delay(name)
        return Response(status=status.HTTP_204_NO_CONTENT)

    class Filter(django_filters.FilterSet):
        active = django_filters.BooleanFilter(field_name="active", label="Active")

        class Meta:
            model = AddOn
            fields = []

    filterset_class = Filter


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
