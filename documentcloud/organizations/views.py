# Django
from rest_framework import viewsets

# Third Party
import django_filters

# DocumentCloud
from documentcloud.organizations.models import Organization
from documentcloud.organizations.serializers import OrganizationSerializer


class OrganizationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrganizationSerializer
    queryset = Organization.objects.none()

    def get_queryset(self):
        return Organization.objects.get_viewable(self.request.user)

    class Filter(django_filters.FilterSet):
        class Meta:
            model = Organization
            fields = {
                "individual": ["exact"],
                "slug": ["exact"],
                "uuid": ["exact"],
                "id": ["in"],
            }

    filterset_class = Filter
