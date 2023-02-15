# Django
from rest_framework import status

# Third Party
import pytest

# DocumentCloud
from documentcloud.common.wikidata import EasyWikidataEntity
from documentcloud.entities.choices import EntityAccess
from documentcloud.entities.models import Entity
from documentcloud.entities.serializers import (
    EntityOccurrenceSerializer,
    EntitySerializer,
)
from documentcloud.entities.tests.factories import (
    EntityFactory,
    EntityOccurrenceFactory,
    PrivateEntityFactory,
)
from documentcloud.users.serializers import UserSerializer


class MockWikidataEntity(EasyWikidataEntity):
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

    def test_retrieve_expand_user(self, client):
        """Test retrieving an entity with an expanded user"""
        entity = PrivateEntityFactory()
        client.force_authenticate(user=entity.user)
        response = client.get(f"/api/entities/{entity.pk}/", {"expand": "user"})
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        user_serializer = UserSerializer(entity.user)
        assert response_json["user"] == user_serializer.data

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

    def test_create_bad_public_values(self, client, user):
        """Test creating a public entity trying to set extra fields"""
        client.force_authenticate(user=user)
        response = client.post(
            "/api/entities/", {"wikidata_id": "Q1050827", "name": "Name"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_non_unique(self, client, user, entity):
        """Test creating a duplicate entity"""
        client.force_authenticate(user=user)
        response = client.post("/api/entities/", {"wikidata_id": entity.wikidata_id})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_private(self, client, user):
        """Test creating a private entity"""
        client.force_authenticate(user=user)
        response = client.post("/api/entities/", {"name": "Name"})
        # Creating private entities is currently not allowed
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_create(self, client, user, mocker, django_assert_num_queries):
        """Create multiple entities"""
        client.force_authenticate(user=user)
        mocker.patch(
            "documentcloud.entities.models.EasyWikidataEntity",
            MockWikidataEntity,
        )
        with django_assert_num_queries(11):
            response = client.post(
                "/api/entities/",
                [
                    {"wikidata_id": "Q1"},
                    {"wikidata_id": "Q2"},
                    {"wikidata_id": "Q3"},
                ],
                format="json",
            )
        assert response.status_code == status.HTTP_201_CREATED
        assert (
            Entity.objects.filter(pk__in=[e["id"] for e in response.json()]).count()
            == 3
        )

    def test_update(self, client, entity, user):
        """Public entities may not be updated"""
        client.force_authenticate(user=user)
        response = client.patch(
            f"/api/entities/{entity.pk}/", {"wikidata_id": "Q9999999"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_destroy(self, client, entity, user):
        """Public entities may not be deleted"""
        client.force_authenticate(user=user)
        response = client.delete(f"/api/entities/{entity.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db()
class TestEntityOccurrenceAPI:
    def test_list(self, client, document):
        """Test listing the entities in a document"""
        size = 10
        EntityOccurrenceFactory.create_batch(size, document=document)
        # create some entities not in this document, they should not be included
        # in the output
        EntityOccurrenceFactory.create_batch(size)
        response = client.get(f"/api/documents/{document.pk}/entities/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["results"]) == size

    def test_get_wikidata_id(self, client, document):
        """Get an entity by its wikidata ID"""
        size = 10
        occurrences = EntityOccurrenceFactory.create_batch(size, document=document)
        response = client.get(
            f"/api/documents/{document.pk}/entities/",
            {"wikidata_id": occurrences[0].entity.wikidata_id},
        )
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        # only one entity for a given wikidata ID
        assert len(response_json["results"]) == 1

    def test_get_name(self, client, document):
        """Get an entity by its name"""
        size = 10
        occurrences = EntityOccurrenceFactory.create_batch(size, document=document)
        response = client.get(
            f"/api/documents/{document.pk}/entities/",
            {"name": occurrences[0].entity.name},
        )
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        # only one entity for a this name
        assert len(response_json["results"]) == 1

    def test_retrieve(self, client, entity_occurrence):
        """Test retrieving an entity occurrence"""
        response = client.get(
            f"/api/documents/{entity_occurrence.document.pk}/entities/"
            f"{entity_occurrence.entity.pk}/"
        )
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        serializer = EntityOccurrenceSerializer(entity_occurrence)
        assert response_json == serializer.data

    def test_create(self, client, document, entity):
        """Test creating an entity occurrence"""
        client.force_authenticate(user=document.user)
        response = client.post(
            f"/api/documents/{document.pk}/entities/", {"entity": entity.pk}
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_no_perm(self, client, user, document, entity):
        """Test creating an entity occurrence on a document you do not own"""
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/documents/{document.pk}/entities/", {"entity": entity.pk}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update(self, client, entity_occurrence):
        """Update an entity occurrence"""
        client.force_authenticate(user=entity_occurrence.document.user)
        response = client.patch(
            f"/api/documents/{entity_occurrence.document.pk}/entities/"
            f"{entity_occurrence.entity.pk}/",
            {"relevance": "0.5"},
        )
        assert response.status_code == status.HTTP_200_OK

    def test_update_no_perm(self, client, user, entity_occurrence):
        """Update an entity occurrence"""
        client.force_authenticate(user=user)
        response = client.patch(
            f"/api/documents/{entity_occurrence.document.pk}/entities/"
            f"{entity_occurrence.entity.pk}/",
            {"relevance": "0.5"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_destroy(self, client, entity_occurrence):
        """Test deleting an entity occurrence"""
        client.force_authenticate(user=entity_occurrence.document.user)
        response = client.delete(
            f"/api/documents/{entity_occurrence.document.pk}/"
            f"entities/{entity_occurrence.entity.pk}/"
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_destroy_no_perm(self, client, user, entity_occurrence):
        """Test deleting an entity occurrence"""
        client.force_authenticate(user=user)
        response = client.delete(
            f"/api/documents/{entity_occurrence.document.pk}/"
            f"entities/{entity_occurrence.entity.pk}/"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
