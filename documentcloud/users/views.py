# Django
from rest_framework import mixins, viewsets

# Third Party
import django_filters
from rest_flex_fields.views import FlexFieldsMixin

# DocumentCloud
from documentcloud.core.filters import ModelChoiceFilter
from documentcloud.organizations.models import Organization
from documentcloud.projects.models import Project
from documentcloud.users.models import User
from documentcloud.users.serializers import UserSerializer


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

    def get_queryset(self):
        return User.objects.get_viewable(self.request.user).prefetch_related(
            "organizations"
        )

    def get_object(self):
        """Allow one to lookup themselves by specifying `me` as the pk"""
        if self.kwargs["pk"] == "me" and self.request.user.is_authenticated:
            return self.request.user
        else:
            return super().get_object()

    class Filter(django_filters.FilterSet):
        organization = ModelChoiceFilter(model=Organization, field_name="organizations")
        project = ModelChoiceFilter(model=Project, field_name="projects")

        class Meta:
            model = User
            fields = ["organization", "project", "name", "username", "uuid"]

    filterset_class = Filter
