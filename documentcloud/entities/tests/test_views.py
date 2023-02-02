# Django
from rest_framework import status

# Third Party
import pytest

# DocumentCloud
from documentcloud.entities.tests.factories import EntityFactory

# pylint: disable=too-many-lines, too-many-public-methods


@pytest.mark.django_db()
class TestEntityAPI:
    def test_create(self, client):
        """Create the entities"""
        entity = EntityFactory()
        client.force_authenticate(user=entity.user)
        response = client.post(f"/api/entities/{entity.pk}/")
        run_commit_hooks()
        assert response.status_code == status.HTTP_200_OK

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
