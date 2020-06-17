# Django
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.db import transaction

# Standard Library
from unittest import mock

# Third Party
import pytest


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
    assert b"<h1>This is a heading</h1>" in response.content
    # check that cache is cleared on save
    flatpage.content = "## Now H2"
    flatpage.save()
    response = client.get("/pages/about/")
    assert b"<h2>Now H2</h2>" in response.content
