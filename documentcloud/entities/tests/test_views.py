# Django
from rest_framework import status

# Third Party
import factory
import pytest

# DocumentCloud
from documentcloud.core.tests import run_commit_hooks
from documentcloud.documents.tests.factories import DocumentFactory

# pylint: disable=too-many-lines, too-many-public-methods


@pytest.mark.django_db()
class TestEntityAPI:
    class EasyWikidataEntity:
        client = None

        def __init__(self, source_wd_entity):
            self.source_wd_entity = source_wd_entity
            pass

        def get_urls(self):
            return self.entity.data.get("sitelinks")

        def get_names(self):
            return self.entity.label.texts

        def get_description(self):
            return self.entity.description.texts

    def test_create(self, client, mocker):
        """Create the entities"""
        print("hey")
        # TODO: Find a setup/teardown place for this.
        # entity = EntityFactory()
        # entity.set_wd_entity()
        # owner = factory.SubFactory("documentcloud.users.tests.factories.UserFactory")
        # TODO: Create this through EntityFactory.
        owner = DocumentFactory().user
        client.force_authenticate(user=owner)
        # print("wikidata_id?", dir(entity))
        response = client.post(
            f"/api/entities/", {"wikidata_id": "Q1050827", "access": 0}
        )
        run_commit_hooks()
        assert response.status_code == status.HTTP_201_OK

    def test_create_404(self, client, user):
        """Return a 404 if the user cannot view the document"""
        document = EntityFactory()
        client.force_authenticate(user=user)
        response = client.post(f"/api/entities/{document.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_403(self, client, document, user):
        """Return a 403 if the user cannot edit the document"""
        client.force_authenticate(user=user)
        response = client.post(f"/api/entities/{document.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete(self, client):
        entity = EntityFactory()
        client.force_authenticate(user=entity.owner)
        response = client.delete(f"/api/entities/{document.pk}/entities/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
