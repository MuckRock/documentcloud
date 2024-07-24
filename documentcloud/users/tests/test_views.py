# Django
from django.db import connection, reset_queries
from django.test.utils import override_settings
from rest_framework import status

# Standard Library
import json
import uuid
from unittest.mock import MagicMock

# Third Party
import pytest
from squarelet_auth.organizations.models import Membership

# DocumentCloud
from documentcloud.documents.choices import Access
from documentcloud.documents.tests.factories import DocumentFactory
from documentcloud.organizations.serializers import OrganizationSerializer
from documentcloud.organizations.tests.factories import OrganizationFactory
from documentcloud.projects.tests.factories import ProjectFactory
from documentcloud.users.serializers import UserSerializer
from documentcloud.users.tests.factories import UserFactory


@pytest.mark.django_db()
class TestUserAPI:
    def test_retrieve_own_email(self, client, user):
        """Test that a user can see their own email"""
        client.force_authenticate(user=user)
        response = client.get("/api/users/me/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert "email" in response_json

    def test_retrieve_another_user_email(self, client, user):
        """Test that a different user cannot see another user's email"""
        another_user = UserFactory()
        client.force_authenticate(user=user)
        response = client.get(f"/api/users/{another_user.pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert "email" not in response_json

    def test_list(self, client):
        """List users"""
        size = 10
        users = UserFactory.create_batch(size)
        OrganizationFactory(members=users)
        client.force_authenticate(user=users[0])
        response = client.get("/api/users/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert len(response_json["results"]) == size

    def test_list_permissions(self, client):
        """List users you can view"""
        # the current user, a user in the same organization, a user in the same
        # project, a user with a public document, a user with a private document
        users = UserFactory.create_batch(5)
        OrganizationFactory(members=users[:2])
        ProjectFactory(user=users[0], collaborators=[users[2]])
        DocumentFactory(user=users[3], access=Access.public)
        DocumentFactory(user=users[4], access=Access.private)
        client.force_authenticate(user=users[0])
        response = client.get("/api/users/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        # you can see all users except for the user with a private document
        assert len(response_json["results"]) == 4

    @pytest.mark.parametrize("expand", ["", "~all", "organization"])
    @override_settings(DEBUG=True)
    def test_list_queries(self, client, expand):
        """Queries should be constant"""
        small_size = 1
        users = UserFactory.create_batch(small_size)
        organization = OrganizationFactory(members=users)
        client.force_authenticate(user=users[0])
        reset_queries()
        client.get(f"/api/users/?expand={expand}")
        num_queries = len(connection.queries)

        size = 10
        users = UserFactory.create_batch(size)
        for user in users:
            Membership.objects.create(user=user, organization=organization)
        client.force_authenticate(user=users[0])
        reset_queries()
        response = client.get(f"/api/users/?expand={expand}")
        assert num_queries == len(connection.queries)
        assert len(response.json()["results"]) == size + small_size

    def test_retrieve(self, client):
        """Test retrieving a user"""
        users = UserFactory.create_batch(2)
        OrganizationFactory(members=users)
        client.force_authenticate(user=users[0])
        response = client.get(f"/api/users/{users[1].pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        serializer = UserSerializer(users[1])
        assert response_json == serializer.data

    def test_retrieve_me(self, client, user):
        """Test retrieving the currently logged in user"""
        client.force_authenticate(user=user)
        response = client.get("/api/users/me/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        context = {"request": MagicMock(), "view": MagicMock()}
        context["request"].user.is_staff = False
        context["view"].kwargs = {"pk": "me"}
        serializer = UserSerializer(user, context=context)
        assert response_json == serializer.data
        assert "is_staff" not in response_json

    def test_retrieve_staff(self, client):
        """Test retrieving as staff exposes `is_staff`"""
        user = UserFactory(is_staff=True)
        client.force_authenticate(user=user)
        response = client.get("/api/users/me/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert "is_staff" in response_json

    def test_retrieve_me_expanded(self, client, user):
        """Test retrieving the currently logged in user"""
        client.force_authenticate(user=user)
        response = client.get("/api/users/me/", {"expand": "organization"})
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        context = {"request": MagicMock(), "view": MagicMock()}
        context["request"].user = user
        organization_serializer = OrganizationSerializer(
            user.organization, context=context
        )
        assert response_json["organization"] == organization_serializer.data

    def test_retrieve_me_anonymous(self, client):
        """me endpoint doesn't work for logged out users"""
        response = client.get("/api/users/me/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update(self, client, user):
        """Test setting a users active org"""
        organization = OrganizationFactory(members=[user])
        assert user.organization != organization
        client.force_authenticate(user=user)
        response = client.patch(
            f"/api/users/{user.pk}/", {"organization": organization.pk}
        )
        assert response.status_code == status.HTTP_200_OK
        assert user.organization == organization

    def test_update_bad_member(self, client, user, organization):
        """Cannot set active organization to an organization you do not belong to"""
        assert user.organization != organization
        client.force_authenticate(user=user)
        response = client.patch(
            f"/api/users/{user.pk}/", {"organization": organization.pk}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_bad_exists(self, client, user):
        """Cannot set active organization to an organization that doesn't exist"""
        client.force_authenticate(user=user)
        response = client.patch(f"/api/users/{user.pk}/", {"organization": 999})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_mailkey(self, client, user):
        """Users may create an upload mail key for themselves"""
        client.force_authenticate(user=user)
        assert user.mailkey is None
        response = client.post("/api/users/mailkey/")
        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.mailkey is not None

    def test_create_mailkey_anon(self, client):
        response = client.post("/api/users/mailkey/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_destroy_mailkey(self, client, user):
        client.force_authenticate(user=user)
        user.mailkey = uuid.uuid4()
        user.save()
        response = client.delete("/api/users/mailkey/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        user.refresh_from_db()
        assert user.mailkey is None
