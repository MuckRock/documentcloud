# Django
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

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
        plugin = self.get_object()
        # XXX validate
        plugin.dispatch(
            self.request.user, request.data["documents"], request.data["parameters"]
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
