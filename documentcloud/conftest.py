# Django
from django.test import RequestFactory
from rest_framework.test import APIClient

# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.tests.factories import DocumentFactory
from documentcloud.users.tests.factories import UserFactory


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def document():
    return DocumentFactory()
