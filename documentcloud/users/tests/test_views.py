# Django
from django.conf import settings
from django.db import connection, reset_queries
from django.test.utils import override_settings
from rest_framework import status

# Standard Library
import json
import uuid
from email.utils import parseaddr
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
        context["view"].action = "retrieve"
        organization_serializer = OrganizationSerializer(
            user.organization, context=context
        )
        assert response_json["organization"] == organization_serializer.data

    def test_retrieve_me_anonymous(self, client):
        """me endpoint doesn't work for logged out users"""
        response = client.get("/api/users/me/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

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

    def test_retrieve_own_email(self, client, user):
        """Test that a user can see their own email"""
        client.force_authenticate(user=user)
        response = client.get("/api/users/me/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert "email" in response_json

    def test_retrieve_another_user_email(self, client):
        """Test that a different user cannot see another user's email"""
        users = UserFactory.create_batch(2)
        OrganizationFactory(members=users)
        client.force_authenticate(user=users[0])
        response = client.get(f"/api/users/{users[1].pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert "email" not in response_json


# Add-Ons which are allowed their own sender, keyed by the permission their
# token carries.  Overridden in tests so they do not depend on the deployed
# addresses.
ADDON_MAIL_FROM = {"klaxon": "Klaxon <klaxon@example.com>"}


@pytest.mark.django_db()
class TestMessageAPI:
    """Add-Ons email their own user through this endpoint

    The API cannot tell which add-on is calling - it only ever sees the user's
    token - so an add-on which may send under its own name is identified by a
    permission embedded in that token when it is issued.
    """

    def send(self, client, **kwargs):
        return client.post(
            "/api/messages/",
            {"subject": "Site changed", "content": "Something happened"},
            **kwargs,
        )

    def test_send(self, client, user, mailoutbox):
        """You may email yourself"""
        client.force_authenticate(user=user)
        response = self.send(client)
        assert response.status_code == status.HTTP_200_OK
        assert len(mailoutbox) == 1
        mail = mailoutbox[0]
        assert mail.subject == "Site changed"
        assert mail.to == [user.email]
        assert "Something happened" in mail.body

    def test_send_anonymous(self, client, mailoutbox):
        """You must be logged in to send a message"""
        response = self.send(client)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not mailoutbox

    def test_send_invalid(self, client, user, mailoutbox):
        """Both subject and content are required"""
        client.force_authenticate(user=user)
        response = client.post("/api/messages/", {"subject": "Site changed"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not mailoutbox

    def test_send_default_sender(self, client, user, mailoutbox):
        """Without a mail permission, the message comes from us"""
        client.force_authenticate(user=user)
        self.send(client)
        mail = mailoutbox[0]
        assert mail.from_email == settings.DEFAULT_FROM_EMAIL
        # the body is branded to match the sender
        from_name, contact_email = parseaddr(settings.DEFAULT_FROM_EMAIL)
        assert from_name in mail.body
        assert contact_email in mail.body

    @override_settings(ADDON_MAIL_FROM=ADDON_MAIL_FROM)
    def test_send_addon_sender(self, client, user, mailoutbox):
        """A token with a mail permission sends under that add-on's name"""
        client.force_authenticate(user=user, token={"permissions": ["klaxon"]})
        self.send(client)
        mail = mailoutbox[0]
        assert mail.from_email == "Klaxon <klaxon@example.com>"
        # and Mailgun is told to route it over that address's domain
        assert mail.envelope_sender == "Klaxon <klaxon@example.com>"
        # the body is branded to match the sender, not to us
        assert "Klaxon" in mail.body
        assert "klaxon@example.com" in mail.body
        assert parseaddr(settings.DEFAULT_FROM_EMAIL)[1] not in mail.body
        # the recipient is still the token's own user
        assert mail.to == [user.email]

    @override_settings(ADDON_MAIL_FROM=ADDON_MAIL_FROM)
    def test_send_unrelated_permission(self, client, user, mailoutbox):
        """A permission with no sender configured uses the default"""
        client.force_authenticate(user=user, token={"permissions": ["processing"]})
        self.send(client)
        assert mailoutbox[0].from_email == settings.DEFAULT_FROM_EMAIL

    @override_settings(ADDON_MAIL_FROM=ADDON_MAIL_FROM)
    def test_send_no_permissions_claim(self, client, user, mailoutbox):
        """A token without a permissions claim at all uses the default"""
        client.force_authenticate(user=user, token={})
        self.send(client)
        assert mailoutbox[0].from_email == settings.DEFAULT_FROM_EMAIL
