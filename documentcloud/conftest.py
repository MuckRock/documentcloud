# Django
from django.test import RequestFactory
from rest_framework.test import APIClient

# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.tests.factories import (
    DocumentFactory,
    NoteFactory,
    SectionFactory,
)
from documentcloud.organizations.tests.factories import OrganizationFactory
from documentcloud.projects.tests.factories import ProjectFactory
from documentcloud.users.tests.factories import UserFactory


def pytest_ignore_collect(path, config):
    """Do not recurse into symlinks when collecting tests
    Used to ignore symlinks we have in processing to the common module
    """
    # pylint: disable=unused-argument
    return path.isdir() and path.islink()


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


@pytest.fixture
def note():
    return NoteFactory()


@pytest.fixture
def section():
    return SectionFactory()


@pytest.fixture
def project():
    return ProjectFactory()


@pytest.fixture
def organization():
    return OrganizationFactory()
