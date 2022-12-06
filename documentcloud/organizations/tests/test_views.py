# Django
from django.conf import settings
from rest_framework import status

# Standard Library
import json

# Third Party
import pytest

# DocumentCloud
from documentcloud.organizations.serializers import OrganizationSerializer
from documentcloud.organizations.tests.factories import (
    OrganizationFactory,
    ProfessionalOrganizationFactory,
)


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

    def test_ai_credits(self, client, pro_organization):
        """Test charging AI credits"""
        response = client.post(
            f"/api/organizations/{pro_organization.pk}/ai_credits/",
            {"ai_credits": 2100},
            HTTP_AUTHORIZATION=f"processing-token {settings.PROCESSING_TOKEN}",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"monthly": 2000, "regular": 100}

    def test_ai_credits_user(self, client, user):
        """Test charging AI credits as a user"""
        client.force_authenticate(user=user)
        organization = ProfessionalOrganizationFactory(members=[user])
        response = client.post(
            f"/api/organizations/{organization.pk}/ai_credits/",
            {"ai_credits": 1},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"monthly": 1, "regular": 0}

    def test_ai_credits_no_auth(self, client, pro_organization):
        """Test charging AI credits with no authentication"""
        response = client.post(
            f"/api/organizations/{pro_organization.pk}/ai_credits/",
            {"ai_credits": 100},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_ai_credits_bad_user(self, client, user):
        """Test charging AI credits as a user not in the organization"""
        client.force_authenticate(user=user)
        organization = ProfessionalOrganizationFactory()
        response = client.post(
            f"/api/organizations/{organization.pk}/ai_credits/",
            {"ai_credits": 1},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_ai_credits_bad_credits(self, client, pro_organization):
        """Test charging AI credits with invalid credit value"""
        response = client.post(
            f"/api/organizations/{pro_organization.pk}/ai_credits/",
            {"ai_credits": -1},
            HTTP_AUTHORIZATION=f"processing-token {settings.PROCESSING_TOKEN}",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_ai_credits_too_many_credits(self, client, pro_organization):
        """Test charging AI credits over the limit"""
        response = client.post(
            f"/api/organizations/{pro_organization.pk}/ai_credits/",
            {"ai_credits": 3000},
            HTTP_AUTHORIZATION=f"processing-token {settings.PROCESSING_TOKEN}",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
