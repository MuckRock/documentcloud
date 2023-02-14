# Django
from rest_framework import status

# Third Party
import pytest

# DocumentCloud
from documentcloud.core.tests import run_commit_hooks
from documentcloud.entities.choices import EntityAccess
from documentcloud.entities.serializers import EntitySerializer
from documentcloud.entities.tests.factories import EntityFactory


class MockWikidataEntity:
    def __init__(self, wikidata_id):
        self.wikidata_id = wikidata_id

    def get_urls(self):
        return {
            "en": "https://en.wikipedia.org/wiki/test",
            "es": "https://es.wikipedia.org/wiki/test",
        }

    def get_names(self):
        return {"en": "test", "es": "prueba"}

    def get_description(self):
        return {"en": "merit assessment", "es": "evaluación de méritos"}


@pytest.mark.django_db()
class TestEntityAPI:
    def test_list(self, client):
        """Test listing all entities"""
        size = 10
        EntityFactory.create_batch(size)
        response = client.get("/api/entities/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["results"]) == size

    def test_get_wikidata_id(self, client):
        """Get an entity by its wikidata ID"""
        size = 10
        entities = EntityFactory.create_batch(size)
        response = client.get(
            "/api/entities/", {"wikidata_id": entities[0].wikidata_id}
        )
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        # only one entity for a given wikidata ID
        assert len(response_json["results"]) == 1

    def test_get_name(self, client):
        """Get an entity by its name"""
        size = 10
        entities = EntityFactory.create_batch(size)
        response = client.get("/api/entities/", {"name": entities[0].name})
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        # only one entity with this name
        assert len(response_json["results"]) == 1

    def test_retrieve(self, client, entity):
        """Test retrieving an entity"""
        response = client.get(f"/api/entities/{entity.pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        serializer = EntitySerializer(entity)
        assert response_json == serializer.data

    def test_create(self, client, user, mocker):
        """Test creating an entity"""
        client.force_authenticate(user=user)
        mocker.patch(
            "documentcloud.entities.models.EasyWikidataEntity",
            MockWikidataEntity,
        )
        response = client.post("/api/entities/", {"wikidata_id": "Q1050827"})
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["access"] == EntityAccess.public
        assert response.data["name"] == "test"

    def test_update(self, client, entity, user):
        """Public entities may not be updated"""
        client.force_authenticate(user=user)
        response = client.patch(
            f"/api/entities/{entity.pk}/", {"wikidata_id": "Q9999999"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete(self, client, entity, user):
        """Public entities may not be deleted"""
        client.force_authenticate(user=user)
        response = client.delete(f"/api/entities/{entity.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
