# Django
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

# Third Party
import django_filters

# DocumentCloud
from documentcloud.core.permissions import (
    DjangoObjectPermissionsOrAnonReadOnly,
    OrganizationAICreditsPermissions,
)
from documentcloud.organizations.exceptions import InsufficientAICreditsError
from documentcloud.organizations.models import Organization
from documentcloud.organizations.serializers import (
    AICreditSerializer,
    OrganizationSerializer,
)


class OrganizationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrganizationSerializer
    queryset = Organization.objects.none()
    permission_classes = (
        DjangoObjectPermissionsOrAnonReadOnly | OrganizationAICreditsPermissions,
    )

    def get_queryset(self):
        self.valid_token = (
            hasattr(self.request, "auth")
            and self.request.auth is not None
            and "processing" in self.request.auth.get("permissions", [])
        )
        if self.valid_token:
            return Organization.objects.all()
        else:
            return Organization.objects.get_viewable(self.request.user)

    @action(detail=True, methods=["post"])
    def ai_credits(self, request, pk=None):
        """Charge AI credits to the organization"""
        # pylint: disable=unused-argument
        if not self.valid_token:
            # only the lambda processing should be allowed to charge AI credits for now
            raise PermissionDenied()
        organization = self.get_object()
        serializer = AICreditSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        try:
            ai_credits = organization.use_ai_credits(
                serializer.validated_data["ai_credits"]
            )
            return Response(ai_credits, status=status.HTTP_200_OK)
        except InsufficientAICreditsError as exc:
            return Response({"amount": exc.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    class Filter(django_filters.FilterSet):
        class Meta:
            model = Organization
            fields = {
                "individual": ["exact"],
                "slug": ["exact"],
                "uuid": ["exact"],
                "id": ["in"],
                "name": ["exact", "istartswith"],
            }

    filterset_class = Filter
