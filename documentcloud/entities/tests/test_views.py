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
    def test_create(self, client, mocker):
        class MockWikidataEntity:
            def get_urls(self):
                return {
                    "en": "https://en.wikipedia.org/wiki/test",
                    "es": "https://es.wikipedia.org/wiki/test",
                }

            def get_names(self):
                return {"en": "test", "es": "prueba"}

            def get_description(self):
                return {"en": "merit assessment", "es": "evaluación de méritos"}

        """Create the entities"""
        # TODO: Create this through EntityFactory.
        owner = DocumentFactory().user
        client.force_authenticate(user=owner)
        # TODO: Is there a setup/teardown place for this?
        mocker.patch(
            "documentcloud.entities.models.Entity.get_wd_entity",
            lambda ignored, also_ignored: MockWikidataEntity(),
        )
        response = client.post(
            f"/api/entities/", {"wikidata_id": "Q1050827", "access": 0}
        )
        run_commit_hooks()
        assert response.status_code == status.HTTP_201_CREATED

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
