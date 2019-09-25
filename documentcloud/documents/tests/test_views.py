# Standard Library
import json

# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.choices import Access
from documentcloud.documents.models import Document, Note
from documentcloud.documents.serializers import DocumentSerializer, NoteSerializer
from documentcloud.documents.tests.factories import DocumentFactory, NoteFactory


@pytest.mark.django_db()
class TestDocumentAPI:
    def test_list(self, client):
        """List documents"""
        size = 10
        DocumentFactory.create_batch(size)
        response = client.get(f"/api/documents/")
        assert response.status_code == 200
        response_json = json.loads(response.content)
        assert len(response_json["results"]) == size

    def test_list_filter(self, client, user):
        """List a subset of documents"""
        size = 5
        DocumentFactory.create_batch(size)
        DocumentFactory.create_batch(size, user=user)
        response = client.get(f"/api/documents/", {"user": user.pk})
        assert response.status_code == 200
        response_json = json.loads(response.content)
        assert len(response_json["results"]) == size

    def test_list_order(self, client):
        """List the documents in order"""
        DocumentFactory(page_count=3)
        DocumentFactory(page_count=1)
        DocumentFactory(page_count=2)
        response = client.get(f"/api/documents/", {"ordering": "page_count"})
        assert response.status_code == 200
        response_json = json.loads(response.content)
        assert [j["page_count"] for j in response_json["results"]] == [1, 2, 3]

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

    def test_retrieve_bad(self, client):
        """Test retrieving a document you do not have access to"""
        document = DocumentFactory(access=Access.private)
        response = client.get(f"/api/documents/{document.pk}/")
        assert response.status_code == 404

    def test_update(self, client, document):
        """Test updating a document"""
        client.force_authenticate(user=document.user)
        title = "New Title"
        response = client.patch(f"/api/documents/{document.pk}/", {"title": title})
        assert response.status_code == 200
        document.refresh_from_db()
        assert document.title == title

    def test_destroy(self, client, document):
        """Test destroying a document"""
        client.force_authenticate(user=document.user)
        response = client.delete(f"/api/documents/{document.pk}/")
        assert response.status_code == 204
        assert not Document.objects.filter(pk=document.pk).exists()


@pytest.mark.django_db()
class TestNoteAPI:
    def test_list(self, client, document):
        """List the notes of a document"""
        size = 10
        NoteFactory.create_batch(size, document=document)
        response = client.get(f"/api/documents/{document.pk}/notes/")
        assert response.status_code == 200
        response_json = json.loads(response.content)
        assert len(response_json["results"]) == size

    def test_create_public(self, client, document):
        """Create a public note"""
        client.force_authenticate(user=document.user)
        response = client.post(
            f"/api/documents/{document.pk}/notes/",
            {
                "title": "Test",
                "content": "Lorem Ipsum",
                "page_number": 1,
                "top": 10,
                "left": 10,
                "bottom": 20,
                "right": 20,
                "access": Access.public,
            },
        )
        assert response.status_code == 201
        response_json = json.loads(response.content)
        assert Note.objects.filter(pk=response_json["id"]).exists()

    def test_create_public_bad(self, client, user, document):
        """You may only create public notes on documents you can edit"""
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/documents/{document.pk}/notes/",
            {
                "title": "Test",
                "content": "Lorem Ipsum",
                "page_number": 1,
                "top": 10,
                "left": 10,
                "bottom": 20,
                "right": 20,
                "access": Access.public,
            },
        )
        assert response.status_code == 400

    def test_create_private(self, client, user, document):
        """Create a private note"""
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/documents/{document.pk}/notes/",
            {
                "title": "Test",
                "content": "Lorem Ipsum",
                "page_number": 1,
                "top": 10,
                "left": 10,
                "bottom": 20,
                "right": 20,
                "access": Access.private,
            },
        )
        assert response.status_code == 201
        response_json = json.loads(response.content)
        assert Note.objects.filter(pk=response_json["id"]).exists()

    def test_retrieve(self, client, note):
        """Test retrieving a note"""

        response = client.get(f"/api/documents/{note.document.pk}/notes/{note.pk}/")
        assert response.status_code == 200
        response_json = json.loads(response.content)
        serializer = NoteSerializer(note)
        assert response_json == serializer.data

    def test_retrieve_bad(self, client):
        """Test retrieving a note you do not have access to"""

        note = NoteFactory(access=Access.private)
        response = client.get(f"/api/documents/{note.document.pk}/notes/{note.pk}/")
        assert response.status_code == 404

    def test_retrieve_bad_document(self, client):
        """Test retrieving a note"""

        note = NoteFactory(document__access=Access.private)
        response = client.get(f"/api/documents/{note.document.pk}/notes/{note.pk}/")
        assert response.status_code == 404

    def test_update(self, client, note):
        """Test updating a note"""
        client.force_authenticate(user=note.user)
        title = "New Title"
        response = client.patch(
            f"/api/documents/{note.document.pk}/notes/{note.pk}/", {"title": title}
        )
        assert response.status_code == 200
        note.refresh_from_db()
        assert note.title == title

    def test_update_access(self, client, note):
        """A note may be switched between public and organization"""
        client.force_authenticate(user=note.user)
        response = client.patch(
            f"/api/documents/{note.document.pk}/notes/{note.pk}/",
            {"access": Access.organization},
        )
        assert response.status_code == 200
        note.refresh_from_db()
        assert note.access == Access.organization

    def test_update_access_bad(self, client, note):
        """A note may not be switched from or to private"""
        client.force_authenticate(user=note.user)
        response = client.patch(
            f"/api/documents/{note.document.pk}/notes/{note.pk}/",
            {"access": Access.private},
        )
        assert response.status_code == 400

    def test_destroy(self, client, note):
        """Test destroying a document"""
        client.force_authenticate(user=note.user)
        response = client.delete(f"/api/documents/{note.document.pk}/notes/{note.pk}/")
        assert response.status_code == 204
        assert not Note.objects.filter(pk=note.pk).exists()
