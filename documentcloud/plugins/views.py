# Django
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

# Third Party
import requests

# DocumentCloud
from documentcloud.plugins.models import Plugin
from documentcloud.plugins.serializers import PluginSerializer


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

    @action(detail=True, url_path="dispatch", methods=["post"])
    def github_dispatch(self, request, pk=None):
        # pylint: disable=unused-argument
        if not request.user.is_authenticated:
            return Response(
                {"error": "You must be logged in to activate an Add-On"},
                status=status.HTTP_403_FORBIDDEN,
            )
        if "parameters" not in request.data:
            return Response(
                {"error": "Missing `parameters`"}, status=status.HTTP_400_BAD_REQUEST
            )
        plugin = self.get_object()
        missing = plugin.validate(request.data["parameters"])
        if missing:
            return Response(
                {"error": f"Missing the following keys from `parameters`: {mising}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            plugin.dispatch(
                self.request.user,
                request.data.get("documents"),
                request.data.get("query"),
                request.data["parameters"],
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        except requests.exceptions.RequestException as exc:
            return Response(
                {"error": exc.args[0]}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
