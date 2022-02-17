# Django
from django.db import transaction
from rest_framework import exceptions, mixins, status, viewsets
from rest_framework.response import Response

# Standard Library
from functools import lru_cache

# Third Party
import requests

# DocumentCloud
from documentcloud.plugins.models import Plugin, PluginRun
from documentcloud.plugins.serializers import PluginRunSerializer, PluginSerializer
from documentcloud.plugins.tasks import find_run_id


class PluginViewSet(viewsets.ModelViewSet):
    serializer_class = PluginSerializer
    queryset = Plugin.objects.none()

    def get_queryset(self):
        return Plugin.objects.get_viewable(self.request.user)

    def perform_create(self, serializer):
        """Specify the user and organization"""
        serializer.save(
            user=self.request.user, organization=self.request.user.organization
        )


class PluginRunViewSet(viewsets.ModelViewSet):
    serializer_class = PluginRunSerializer
    queryset = PluginRun.objects.none()
    lookup_field = "uuid"

    @lru_cache()
    def get_queryset(self):
        """Only fetch plugin runs viewable to this user"""
        return PluginRun.objects.get_viewable(self.request.user)

    def perform_create(self, serializer):
        if "parameters" not in self.request.data:
            raise exceptions.ValidationError({"parameters": "Missing"})
        missing = serializer.plugin.validate(self.request.data["parameters"])
        if missing:
            raise exceptions.ValidationError({"parameters": f"Missing keys: {missing}"})
        try:
            with transaction.atomic():
                run = serializer.save(user=self.request.user)
                run.plugin.dispatch(
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

    def retrieve(self, request, *args, **kwargs):
        """Update status before retrieving if necessary"""
        # pylint: disable=unused-argument
        instance = self.get_object()
        if instance.status in ["queued", "in_progress"]:
            status_ = instance.get_status()
            if status_ is not None:
                instance.status = status_
                instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
