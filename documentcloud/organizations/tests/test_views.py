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
        response = client.get("/api/organizations/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert len(response_json["results"]) == size

    def test_list_id_in_filter(self, client):
        """List organizations"""
        size = 10
        orgs = OrganizationFactory.create_batch(size)
        some_ids = [str(o.id) for o in orgs[:5]]
        response = client.get("/api/organizations/", {"id__in": ",".join(some_ids)})
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert len(response_json["results"]) == len(some_ids)

    def test_list_filter(self, client):
        """List organizations"""
        names = ["abcdef", "ABC123", "abcxyz", "xyz123", "x12345", "qwerty"]
        for name in names:
            OrganizationFactory.create(name=name)

        prefixes = [("abc", 3), ("a", 3), ("x", 2), ("xyz", 1), ("qwerty", 1)]
        for prefix, size in prefixes:
            response = client.get("/api/organizations/", {"name__istartswith": prefix})
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
