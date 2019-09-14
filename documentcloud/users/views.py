# Django
from rest_framework import viewsets

# Third Party
import django_filters

# DocumentCloud
from documentcloud.core.filters import ModelChoiceFilter
from documentcloud.organizations.models import Organization
from documentcloud.users.models import User
from documentcloud.users.serializers import UserSerializer


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    queryset = User.objects.none()

    def get_queryset(self):
        return User.objects.get_viewable(self.request.user).prefetch_related(
            "organizations"
        )

    def get_object(self):
        """Allow one to lookup themselves by specifying `me` as the pk"""
        if self.kwargs["pk"] == "me":
            return self.request.user
        else:
            return super().get_object()

    class Filter(django_filters.FilterSet):
        organizations = ModelChoiceFilter(model=Organization)

        class Meta:
            model = User
            fields = ["organizations", "name", "username", "uuid"]

    filterset_class = Filter
