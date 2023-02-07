# Django
from rest_framework import status

# Third Party
import factory
import pytest

# DocumentCloud
from documentcloud.core.tests import run_commit_hooks
from documentcloud.documents.tests.factories import DocumentFactory, EntityFactory
from documentcloud.entities.choices import EntityAccess

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
        response = client.post(f"/api/entities/", {"wikidata_id": "Q1050827"})
        run_commit_hooks()
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["access"] == EntityAccess.public

    def test_delete(self, client):
        entity = EntityFactory()
        client.force_authenticate(user=DocumentFactory().user)
        response = client.delete(f"/api/entities/{entity.pk}")
        response.status_code == status.HTTP_204_NO_CONTENT
