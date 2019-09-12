# Standard Library
import json

# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.models import Document
from documentcloud.documents.serializers import DocumentSerializer
from documentcloud.documents.tests.factories import DocumentFactory


@pytest.mark.django_db()
class TestDocumentAPI:
    # pylint: disable=no-self-use

    def test_list(self, client):
        size = 10
        DocumentFactory.create_batch(size)
        response = client.get(f"/api/documents/")
        assert response.status_code == 200
        response_json = json.loads(response.content)
        assert len(response_json) == size

    def test_create(self, client, user):
        """Upload a document with a file and a title"""
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/documents/",
            {"title": "Test", "file_url": "http://www.example.com/test.pdf"},
        )
        assert response.status_code == 201
        response_json = json.loads(response.content)
        assert Document.objects.filter(pk=response_json["id"]).exists()

    def test_retrieve(self, client, document):
        """Test retrieving a document"""
        response = client.get(f"/api/documents/{document.pk}/")
        assert response.status_code == 200
        response_json = json.loads(response.content)
        serializer = DocumentSerializer(document)
        assert response_json == serializer.data

    def test_update(self, client, document):
        """Test updating a document"""
        title = "New Title"
        response = client.patch(f"/api/documents/{document.pk}/", {"title": title})
        assert response.status_code == 200
        document.refresh_from_db()
        assert document.title == title

    def test_destroy(self, client, document):
        """Test destroying a document"""
        response = client.delete(f"/api/documents/{document.pk}/")
        assert response.status_code == 204
        assert not Document.objects.filter(pk=document.pk).exists()
