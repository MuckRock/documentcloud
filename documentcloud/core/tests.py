# Django
from django.conf import settings
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.core import mail as django_mail
from django.db import transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework.exceptions import AuthenticationFailed

# Standard Library
import hashlib
import hmac
import time
import uuid
from email.utils import parseaddr
from unittest import mock

# Third Party
import pytest
import requests
from rest_framework_simplejwt.settings import api_settings

# DocumentCloud
from documentcloud.core.authentication import SquareletJWTAuthentication
from documentcloud.core.mail import send_mail
from documentcloud.users.tests.factories import UserFactory


def run_commit_hooks():
    """
    Fake transaction commit to run delayed on_commit functions
    https://medium.com/gitux/speed-up-django-transaction-hooks-tests-6de4a558ef96
    """
    with mock.patch(
        "django.db.backends.base.base.BaseDatabaseWrapper.validate_no_atomic_block",
        lambda a: False,
    ):
        transaction.get_connection().run_and_clear_commit_hooks()


@pytest.mark.django_db()
def test_flatpage_markdown(client):
    flatpage = FlatPage.objects.create(
        url="/about/", title="About", content="# This is a heading"
    )
    flatpage.sites.add(Site.objects.get_current())
    response = client.get("/pages/about/")
    assert b'<h1 id="this-is-a-heading">This is a heading</h1>' in response.content
    # check that cache is cleared on save
    flatpage.content = "## Now H2"
    flatpage.save()
    response = client.get("/pages/about/")
    assert b'<h2 id="now-h2">Now H2</h2>' in response.content


class TestMailgunView(TestCase):
    """Tests for the mailgun email upload view"""

    def sign(self, data):
        """Add a valid mailgun signature to POST data"""
        token = "testtoken"
        timestamp = int(time.time())
        signature = hmac.new(
            key=settings.MAILGUN_API_KEY.encode("utf8"),
            msg=f"{timestamp}{token}".encode("utf8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
        data["token"] = token
        data["timestamp"] = timestamp
        data["signature"] = signature

    def mailgun_post(self, to_addr, attachments="[]", sign=True):
        data = {"To": to_addr, "attachments": attachments}
        if sign:
            self.sign(data)
        return self.client.post(reverse("mailgun"), data)

    def test_valid_mailkey(self):
        user = UserFactory(mailkey=uuid.uuid4())
        response = self.mailgun_post(f"{user.mailkey}@uploads.documentcloud.org")
        assert response.status_code == 200

    def test_quoted_to_header(self):
        """Mailgun sometimes sends To as '"mailkey@domain" <mailkey@domain>'"""
        user = UserFactory(mailkey=uuid.uuid4())
        to_addr = (
            f'"{user.mailkey}@uploads.documentcloud.org"'
            f" <{user.mailkey}@uploads.documentcloud.org>"
        )
        response = self.mailgun_post(to_addr)
        assert response.status_code == 200

    def test_unknown_mailkey(self):
        response = self.mailgun_post("doesnotexist@uploads.documentcloud.org")
        assert response.status_code == 200

    def test_invalid_signature(self):
        user = UserFactory(mailkey=uuid.uuid4())
        response = self.mailgun_post(
            f"{user.mailkey}@uploads.documentcloud.org", sign=False
        )
        assert response.status_code == 403


@pytest.mark.django_db()
class TestSquareletJWTAuthentication:
    """Tests for lazy user provisioning during JWT authentication"""

    def token(self, user_uuid):
        """Build a minimal validated token carrying the user's uuid claim"""
        return {api_settings.USER_ID_CLAIM: str(user_uuid)}

    @mock.patch("documentcloud.core.authentication.squarelet_update_or_create")
    @mock.patch("documentcloud.core.authentication.squarelet_get")
    def test_existing_user(self, mock_get, mock_update):
        """A user that already exists locally is returned without a callback"""
        user = UserFactory()
        auth = SquareletJWTAuthentication()

        result = auth.get_user(self.token(user.uuid))

        assert result == user
        mock_get.assert_not_called()
        mock_update.assert_not_called()

    @mock.patch(
        "documentcloud.core.authentication.squarelet_settings.DISABLE_CREATE", False
    )
    @mock.patch("documentcloud.core.authentication.squarelet_update_or_create")
    @mock.patch("documentcloud.core.authentication.squarelet_get")
    def test_lazy_provision_missing_user(self, mock_get, mock_update):
        """A missing user is fetched from Squarelet, created, and returned"""
        missing_uuid = uuid.uuid4()
        data = {"preferred_username": "newuser", "organizations": []}
        mock_get.return_value.json.return_value = data
        # Simulate squarelet_update_or_create creating the local mirror row
        mock_update.side_effect = lambda _uuid, _data: UserFactory(uuid=missing_uuid)
        auth = SquareletJWTAuthentication()

        result = auth.get_user(self.token(missing_uuid))

        assert result.uuid == missing_uuid
        mock_get.assert_called_once_with(f"/api/users/{missing_uuid}/")
        # The uuid comes off the JWT claim as a string, matching how the
        # webhook's pull_data task calls squarelet_update_or_create
        mock_update.assert_called_once_with(str(missing_uuid), data)

    @mock.patch("documentcloud.core.authentication.squarelet_update_or_create")
    @mock.patch("documentcloud.core.authentication.squarelet_get")
    def test_invalid_token_not_provisioned(self, mock_get, mock_update):
        """A token without a user claim must 401 without contacting Squarelet"""
        auth = SquareletJWTAuthentication()

        with pytest.raises(AuthenticationFailed):
            auth.get_user({})

        mock_get.assert_not_called()
        mock_update.assert_not_called()

    @mock.patch(
        "documentcloud.core.authentication.squarelet_settings.DISABLE_CREATE", False
    )
    @mock.patch("documentcloud.core.authentication.squarelet_update_or_create")
    @mock.patch("documentcloud.core.authentication.squarelet_get")
    def test_squarelet_fetch_fails(self, mock_get, mock_update):
        """If the Squarelet fetch fails, the request still 401s"""
        missing_uuid = uuid.uuid4()
        mock_get.side_effect = requests.exceptions.RequestException
        auth = SquareletJWTAuthentication()

        with pytest.raises(AuthenticationFailed):
            auth.get_user(self.token(missing_uuid))

        mock_update.assert_not_called()

    @mock.patch(
        "documentcloud.core.authentication.squarelet_settings.DISABLE_CREATE", True
    )
    @mock.patch("documentcloud.core.authentication.squarelet_update_or_create")
    @mock.patch("documentcloud.core.authentication.squarelet_get")
    def test_disable_create_skips_provisioning(self, mock_get, mock_update):
        """When SQUARELET_DISABLE_CREATE is set, missing users still 401"""
        missing_uuid = uuid.uuid4()
        auth = SquareletJWTAuthentication()

        with pytest.raises(AuthenticationFailed):
            auth.get_user(self.token(missing_uuid))

        mock_get.assert_not_called()
        mock_update.assert_not_called()


@pytest.mark.django_db()
class TestEmailSenderDomain:
    """Which domain Mailgun sends over

    Anymail only intuits the sending domain from the From address when
    MAILGUN_SENDER_DOMAIN is unset, and production sets it.  So mail sent under
    an Add-On's own address has to override it per-message, via the envelope
    sender, or it goes out over our domain and fails DMARC alignment.
    """

    def domain(self, mail):
        """The domain Anymail would route this message over"""
        return parseaddr(mail.envelope_sender)[1].rpartition("@")[2]

    def test_default_sender_keeps_configured_domain(self, user):
        """Our own mail sets no envelope sender, so the global setting stands"""
        send_mail(subject="Hello", user=user, template="core/email/base.html")
        mail = django_mail.outbox[0]
        assert not hasattr(mail, "envelope_sender")

    def test_addon_sender_overrides_domain(self, user):
        """An Add-On's mail is routed over its own domain"""
        send_mail(
            subject="Site changed",
            user=user,
            template="core/email/base.html",
            from_email="Klaxon <no-reply@klaxoncloud.org>",
        )
        mail = django_mail.outbox[0]
        assert mail.from_email == "Klaxon <no-reply@klaxoncloud.org>"
        assert self.domain(mail) == "klaxoncloud.org"

    def test_addon_sender_domain_is_routable(self, user):
        """Mailgun 200s with a junk body if the domain contains a slash, and
        Anymail guards against it - the address must not smuggle one through
        """
        send_mail(
            subject="Site changed",
            user=user,
            template="core/email/base.html",
            from_email=settings.ADDON_MAIL_FROM["klaxon"],
        )
        domain = self.domain(django_mail.outbox[0])
        assert domain
        assert "/" not in domain
        assert (
            domain
            == parseaddr(settings.ADDON_MAIL_FROM["klaxon"])[1].rpartition("@")[2]
        )
