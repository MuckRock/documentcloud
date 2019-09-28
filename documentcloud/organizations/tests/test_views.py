# Django
from rest_framework import status

# Standard Library
import json

# Third Party
import pytest

# DocumentCloud
from documentcloud.organizations.serializers import OrganizationSerializer
from documentcloud.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db()
class TestOrganizationAPI:
    def test_list(self, client):
        """List organizations"""
        size = 10
        OrganizationFactory.create_batch(size)
        response = client.get(f"/api/organizations/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert len(response_json["results"]) == size

    def test_retrieve(self, client, organization):
        """Test retrieving an organization"""
        response = client.get(f"/api/organizations/{organization.pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        serializer = OrganizationSerializer(organization)
        assert response_json == serializer.data

    def test_retrieve_bad(self, client):
        """Cannot view a private organization"""
        organization = OrganizationFactory(private=True)
        response = client.get(f"/api/organizations/{organization.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
