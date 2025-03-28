# Django
from rest_framework import mixins, permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

# Standard Library
import uuid

# Third Party
import django_filters
from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_flex_fields.views import FlexFieldsMixin

# DocumentCloud
from documentcloud.core.filters import ModelMultipleChoiceFilter
from documentcloud.core.mail import send_mail
from documentcloud.organizations.models import Organization
from documentcloud.projects.models import Project
from documentcloud.users.models import User
from documentcloud.users.serializers import MessageSerializer, UserSerializer


class UserViewSet(
    # Cannot create or destroy users
    FlexFieldsMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = UserSerializer
    queryset = User.objects.none()
    permit_list_expands = ["organization"]

    @extend_schema(
        request=None,
        responses={200: UserSerializer(many=True)},
        examples=[
            OpenApiExample(
                "List Users",
                description="A request to retrieve a list of users.",
                value=[
                    {
                        "id": 20323,
                        "avatar_url": "",
                        "name": "Michael Morisy",
                        "organization": 1,
                        "organizations": [1, 24517],
                        "admin_organizations": [1, 24517],
                        "username": "Granicus",
                        "uuid": "cd6b2083-51b0-4f29-bed6-82b0bedfeb23",
                        "verified_journalist": True,
                    },
                    {
                        "id": 24282,
                        "avatar_url": "",
                        "name": "Michael Morisy",
                        "organization": 3168,
                        "organizations": [10147, 3168],
                        "admin_organizations": [10147, 3168],
                        "username": "MichaelMorisy_IfdAklyU",
                        "uuid": "bed05c7e-557d-4956-a410-0218ac18d973",
                        "verified_journalist": True,
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
        responses={200: UserSerializer},
        examples=[
            OpenApiExample(
                "Retrieve User",
                description="A response for a retrieve request of a specific user by ID.",  # pylint:disable=line-too-long
                value={
                    "id": 20323,
                    "avatar_url": "",
                    "name": "Michael Morisy",
                    "organization": 1,
                    "organizations": [1, 24517],
                    "admin_organizations": [1, 24517],
                    "username": "Granicus",
                    "uuid": "cd6b2083-51b0-4f29-bed6-82b0bedfeb23",
                    "verified_journalist": True,
                },
                response_only=True,
            ),
        ],
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    def get_queryset(self):
        return User.objects.get_viewable(self.request.user).preload(
            self.request.user, self.request.query_params.get("expand", "")
        )

    def get_object(self):
        """Allow one to lookup themselves by specifying `me` as the pk"""
        if self.kwargs["pk"] == "me" and self.request.user.is_authenticated:
            return self.get_queryset().get(pk=self.request.user.pk)
        else:
            return super().get_object()

    @extend_schema(
        request=inline_serializer("mailkey", {}),
        responses={
            201: inline_serializer("mailkey", {"mailkey": serializers.UUIDField()})
        },
    )
    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def mailkey(self, request):
        """
        Create a new mailkey for yourself.
        This allows you to upload documents via email.
        """
        if not self.request.user.is_authenticated:
            return Response({"error": "Unauthenticated"}, status=401)

        self.request.user.mailkey = uuid.uuid4()
        self.request.user.save()
        send_mail(
            subject="A private upload email address was created for your account",
            user=self.request.user,
            template="core/email/mailkey.html",
        )
        return Response({"mailkey": self.request.user.mailkey})

    @extend_schema(
        request=None,
        responses=None,
    )
    @mailkey.mapping.delete
    def delete_mailkey(self, request):
        """Delete an existing mailkey"""
        if not self.request.user.is_authenticated:
            return Response({"error": "Unauthenticated"}, status=401)

        self.request.user.mailkey = None
        self.request.user.save()
        send_mail(
            subject="A private upload email address was deleted from your account",
            user=self.request.user,
            template="core/email/mailkey_delete.html",
        )
        return Response(status=204)

    class Filter(django_filters.FilterSet):
        organization = ModelMultipleChoiceFilter(
            model=Organization,
            field_name="organizations",
            help_text="The user's active organization",
        )
        project = ModelMultipleChoiceFilter(
            model=Project,
            field_name="projects",
            help_text="ID of projects the user has access to",
        )
        name = django_filters.CharFilter(help_text="The user's full name")
        username = django_filters.CharFilter(help_text="The user's username")
        uuid = django_filters.UUIDFilter(
            help_text=(
                "UUID which links this user to the corresponding user "
                "on the MuckRock Accounts Site"
            )
        )

        class Meta:
            model = User
            fields = {
                # "organization": ["exact"],
                # "project": ["exact"],
                "name": ["exact", "istartswith"],
                "username": ["exact"],
                "uuid": ["exact"],
                "id": ["in"],
            }

    filterset_class = Filter


class MessageView(APIView):
    """A view to allow you to email yourself via API"""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MessageSerializer

    def post(self, request, format=None):
        """Send yourself an email, used by Add-Ons."""
        # pylint: disable=redefined-builtin, unused-argument
        serializer = MessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        send_mail(
            subject=serializer.validated_data["subject"],
            user=request.user,
            template="core/email/base.html",
            extra_context={"content": serializer.validated_data["content"]},
        )
        return Response(serializer.data)
