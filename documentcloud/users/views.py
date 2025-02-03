# Django
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

# Standard Library
import uuid

# Third Party
import django_filters
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
