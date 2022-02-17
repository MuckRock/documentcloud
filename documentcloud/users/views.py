# Django
from rest_framework import mixins, permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

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

    class Filter(django_filters.FilterSet):
        organization = ModelMultipleChoiceFilter(
            model=Organization, field_name="organizations"
        )
        project = ModelMultipleChoiceFilter(model=Project, field_name="projects")

        class Meta:
            model = User
            fields = {
                # "organization": ["exact"],
                # "project": ["exact"],
                "name": ["exact", "istartswith"],
                "username": ["exact"],
                "uuid": ["exact"],
            }

    filterset_class = Filter


class MessageView(APIView):
    """A view to allow you to email yourself via API"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        """Send youself an email."""
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
