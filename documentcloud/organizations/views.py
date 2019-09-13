# Django
from rest_framework import viewsets

# DocumentCloud
from documentcloud.organizations.models import Organization
from documentcloud.organizations.serializers import OrganizationSerializer


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    queryset = Organization.objects.none()

    def get_queryset(self):
        return self.request.user.organizations.all()
