# Django
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.db import transaction
from django.test import TestCase
from django.urls import reverse

# Standard Library
import hashlib
import hmac
import time
import uuid
from unittest import mock

# Third Party
import pytest

# DocumentCloud
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
            key="".encode("utf8"),
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
