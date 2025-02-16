# Django
from django.db.models.expressions import F, Value
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

# Third Party
import django_filters
from drf_spectacular.utils import OpenApiExample, extend_schema

# DocumentCloud
from documentcloud.addons.models import AddOnRun
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
    permission_classes = (DjangoObjectPermissionsOrAnonReadOnly,)

    @extend_schema(
        request=None,
        responses={200: OrganizationSerializer(many=True)},
        examples=[
            OpenApiExample(
                "List Organizations",
                description="A request to retrieve a list of organizations.",
                value=[
                    {
                        "id": 1,
                        "avatar_url": "https://cdn.muckrock.com/static/images/avatars/organization.png", #pylint:disable=line-too-long
                        "individual": False,
                        "name": "DocumentCloud",
                        "slug": "dcloud",
                        "uuid": "99875da4-7b70-4150-b854-7ba5a3951f99",
                    },
                    {
                        "id": 2,
                        "avatar_url": "https://cdn.muckrock.com/static/images/avatars/organization.png", #pylint:disable=line-too-long
                        "individual": False,
                        "name": "Talking Points Memo",
                        "slug": "tpm",
                        "uuid": "02959701-72b6-4146-aec8-19747f8d47b6",
                    },
                ],
                response_only=True,
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=None,
        responses={200: OrganizationSerializer},
        examples=[
            OpenApiExample(
                "Retrieve Organization",
                description="A response for a retrieve request of a specific organization by ID.", #pylint:disable=line-too-long
                value={
                    "id": 1,
                    "avatar_url": "https://cdn.muckrock.com/static/images/avatars/organization.png", #pylint:disable=line-too-long
                    "individual": False,
                    "name": "DocumentCloud",
                    "slug": "dcloud",
                    "uuid": "99875da4-7b70-4150-b854-7ba5a3951f99",
                },
                response_only=True,
            ),
        ],
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    def get_queryset(self):
        self.valid_token = (
            hasattr(self.request, "auth")
            and self.request.auth is not None
            and "processing" in self.request.auth.get("permissions", [])
        )
        organizations = Organization.objects.select_related("entitlement")
        if self.valid_token:
            return organizations
        else:
            return organizations.get_viewable(self.request.user)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[OrganizationAICreditsPermissions],
    )
    def ai_credits(self, request, pk=None):
        """Charge AI credits to the organization"""
        # pylint: disable=unused-argument
        organization = self.get_object()
        serializer = AICreditSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        try:
            if self.valid_token:
                user_id = serializer.validated_data["user_id"]
            else:
                user_id = request.user.pk
            ai_credits = organization.use_ai_credits(
                serializer.validated_data["ai_credits"],
                user_id,
                serializer.validated_data.get("note", ""),
            )
            run_id = serializer.validated_data.get("addonrun_id")
            if run_id:
                AddOnRun.objects.filter(uuid=run_id).update(
                    credits_spent=F("credits_spent")
                    + Value(serializer.validated_data["ai_credits"])
                )
            return Response(ai_credits, status=status.HTTP_200_OK)
        except InsufficientAICreditsError as exc:
            return Response({"amount": exc.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    class Filter(django_filters.FilterSet):
        individual = django_filters.BooleanFilter(
            help_text="Is this organization for the sole use of an individual."
        )
        slug = django_filters.CharFilter(
            help_text="The slug is a URL-safe version of the organization name."
        )
        uuid = django_filters.UUIDFilter(
            help_text=(
                "UUID which links this organization to the "
                "corresponding organization on the MuckRock Accounts Site."
            )
        )
        name = django_filters.CharFilter(help_text="The name of the organization.")

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
