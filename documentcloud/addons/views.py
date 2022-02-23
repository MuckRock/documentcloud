# Django
from django.db import transaction
from rest_framework import exceptions, mixins, status, viewsets
from rest_framework.response import Response

# Standard Library
from functools import lru_cache

# Third Party
import requests
from django_filters import rest_framework as django_filters
from rest_flex_fields import FlexFieldsModelViewSet
from rest_flex_fields.utils import is_expanded

# DocumentCloud
from documentcloud.addons.models import AddOn, AddOnRun
from documentcloud.addons.serializers import AddOnRunSerializer, AddOnSerializer
from documentcloud.addons.tasks import find_run_id


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
        if "parameters" not in self.request.data:
            raise exceptions.ValidationError({"parameters": "Missing"})
        missing = serializer.validated_data["addon"].validate(
            self.request.data["parameters"]
        )
        if missing:
            raise exceptions.ValidationError({"parameters": f"Missing keys: {missing}"})
        try:
            with transaction.atomic():
                run = serializer.save(user=self.request.user)
                run.addon.dispatch(
                    run.uuid,
                    self.request.user,
                    self.request.data.get("documents"),
                    self.request.data.get("query"),
                    self.request.data["parameters"],
                )
                transaction.on_commit(lambda: find_run_id.delay(run.uuid))
        except requests.exceptions.RequestException as exc:
            raise exceptions.ValidationError(
                exc.args[0], code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    class Filter(django_filters.FilterSet):
        class Meta:
            model = AddOnRun
            fields = {"dismissed": ["exact"]}

    filterset_class = Filter
