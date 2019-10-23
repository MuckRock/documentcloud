# Django
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

# Standard Library
import json

# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.choices import Access
from documentcloud.documents.models import Document, Note, Section
from documentcloud.documents.serializers import (
    DocumentSerializer,
    NoteSerializer,
    SectionSerializer,
)
from documentcloud.documents.tests.factories import (
    DocumentFactory,
    EntityDateFactory,
    EntityFactory,
    NoteFactory,
    SectionFactory,
)


@pytest.mark.django_db()
class TestDocumentAPI:
    def test_list(self, client):
        """List documents"""
        size = 10
        DocumentFactory.create_batch(size)
        response = client.get(f"/api/documents/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert len(response_json["results"]) == size

    def test_list_filter(self, client, user):
        """List a subset of documents"""
        size = 5
        client.force_authenticate(user=user)
        DocumentFactory.create_batch(size)
        DocumentFactory.create_batch(size, user=user)
        response = client.get(f"/api/documents/", {"user": user.pk})
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert len(response_json["results"]) == size

    def test_list_order(self, client):
        """List the documents in order"""
        DocumentFactory(page_count=3)
        DocumentFactory(page_count=1)
        DocumentFactory(page_count=2)
        response = client.get(f"/api/documents/", {"ordering": "page_count"})
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert [j["page_count"] for j in response_json["results"]] == [1, 2, 3]

    def test_create(self, client, user):
        """Upload a document with a file and a title"""
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/documents/",
            {"title": "Test", "file_url": "http://www.example.com/test.pdf"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = json.loads(response.content)
        assert Document.objects.filter(pk=response_json["id"]).exists()

    def test_create_bad_file_and_url(self, client, user):
        """May not specify `file` and `file_url`"""
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/documents/",
            {
                "title": "Test",
                "file": SimpleUploadedFile("hello.txt", b"123"),
                "file_url": "http://www.example.com/test.pdf",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_bad_no_file(self, client, user):
        """May not specify `file` and `file_url`"""
        client.force_authenticate(user=user)
        response = client.post(f"/api/documents/", {"title": "Test"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_retrieve(self, client, document):
        """Test retrieving a document"""
        response = client.get(f"/api/documents/{document.pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        serializer = DocumentSerializer(document)
        assert response_json == serializer.data
        assert response_json["access"] == "public"

    def test_retrieve_bad(self, client):
        """Test retrieving a document you do not have access to"""
        document = DocumentFactory(access=Access.private)
        response = client.get(f"/api/documents/{document.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update(self, client, document):
        """Test updating a document"""
        client.force_authenticate(user=document.user)
        title = "New Title"
        response = client.patch(
            f"/api/documents/{document.pk}/", {"title": title, "access": "organization"}
        )
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.title == title
        assert document.access == Access.organization

    def test_update_bad_file(self, client, document):
        """You may not update the file"""
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/documents/{document.pk}/",
            {"file": SimpleUploadedFile("hello.txt", b"123")},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_bad_file_url(self, client, document):
        """You may not update the file url"""
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/documents/{document.pk}/",
            {"file_url": "https://www.example.com/2.pdf"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_bad_access(self, client, document):
        """You may not make a document invisible"""
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/documents/{document.pk}/", {"access": "invisible"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_bad_processing_token(self, client, document):
        """Only the processing functions with a token may modify certain fields"""
        client.force_authenticate(user=document.user)
        response = client.patch(f"/api/documents/{document.pk}/", {"page_count": 42})
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.page_count != 42

    def test_update_processing_token(self, client, document):
        """Only the processing functions with a token may modify certain fields"""
        response = client.patch(
            f"/api/documents/{document.pk}/",
            {"page_count": 42},
            HTTP_AUTHORIZATION=f"processing-token {settings.PROCESSING_TOKEN}",
        )
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.page_count == 42

    def test_destroy(self, client, document):
        """Test destroying a document"""
        client.force_authenticate(user=document.user)
        response = client.delete(f"/api/documents/{document.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Document.objects.filter(pk=document.pk).exists()


@pytest.mark.django_db()
class TestNoteAPI:
    def test_list(self, client, document):
        """List the notes of a document"""
        size = 10
        NoteFactory.create_batch(size, document=document)
        response = client.get(f"/api/documents/{document.pk}/notes/")
        assert response.status_code == status.HTTP_200_OK
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
                "access": "public",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
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
                "access": "public",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

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
                "access": "private",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = json.loads(response.content)
        assert Note.objects.filter(pk=response_json["id"]).exists()

    def test_retrieve(self, client, note):
        """Test retrieving a note"""

        response = client.get(f"/api/documents/{note.document.pk}/notes/{note.pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        serializer = NoteSerializer(note)
        assert response_json == serializer.data

    def test_retrieve_bad(self, client):
        """Test retrieving a note you do not have access to"""

        note = NoteFactory(access=Access.private)
        response = client.get(f"/api/documents/{note.document.pk}/notes/{note.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_bad_document(self, client):
        """Test retrieving a note on a document you do not have access to"""

        note = NoteFactory(document__access=Access.private)
        response = client.get(f"/api/documents/{note.document.pk}/notes/{note.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update(self, client, note):
        """Test updating a note"""
        client.force_authenticate(user=note.user)
        title = "New Title"
        response = client.patch(
            f"/api/documents/{note.document.pk}/notes/{note.pk}/", {"title": title}
        )
        assert response.status_code == status.HTTP_200_OK
        note.refresh_from_db()
        assert note.title == title

    def test_update_access(self, client, note):
        """A note may be switched between public and organization"""
        client.force_authenticate(user=note.user)
        response = client.patch(
            f"/api/documents/{note.document.pk}/notes/{note.pk}/",
            {"access": "organization"},
        )
        assert response.status_code == status.HTTP_200_OK
        note.refresh_from_db()
        assert note.access == Access.organization

    def test_update_access_bad_to_private(self, client, note):
        """A note may not be switched from public/organization to private"""
        client.force_authenticate(user=note.user)
        response = client.patch(
            f"/api/documents/{note.document.pk}/notes/{note.pk}/", {"access": "private"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_access_bad_from_private(self, client):
        """A note may not be switched from public/organization to private"""
        note = NoteFactory(access=Access.private)
        client.force_authenticate(user=note.user)
        response = client.patch(
            f"/api/documents/{note.document.pk}/notes/{note.pk}/",
            {"access": "organization"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_destroy(self, client, note):
        """Test destroying a document"""
        client.force_authenticate(user=note.user)
        response = client.delete(f"/api/documents/{note.document.pk}/notes/{note.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Note.objects.filter(pk=note.pk).exists()


@pytest.mark.django_db()
class TestSectionAPI:
    def test_list(self, client, document):
        """List the sections of a document"""
        size = 10
        SectionFactory.create_batch(size, document=document)
        response = client.get(f"/api/documents/{document.pk}/sections/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert len(response_json["results"]) == size

    def test_create(self, client, document):
        """Create a section"""
        client.force_authenticate(user=document.user)
        response = client.post(
            f"/api/documents/{document.pk}/sections/",
            {"title": "Test", "page_number": 1},
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = json.loads(response.content)
        assert Section.objects.filter(pk=response_json["id"]).exists()

    def test_create_bad(self, client, user, document):
        """You may only create sections on documents you can edit"""
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/documents/{document.pk}/sections/",
            {"title": "Test", "page_number": 1},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_retrieve(self, client, section):
        """Test retrieving a section"""

        response = client.get(
            f"/api/documents/{section.document.pk}/sections/{section.pk}/"
        )
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        serializer = SectionSerializer(section)
        assert response_json == serializer.data

    def test_retrieve_bad_document(self, client):
        """Test retrieving a section on a document you do not have access to"""

        section = SectionFactory(document__access=Access.private)
        response = client.get(
            f"/api/documents/{section.document.pk}/sections/{section.pk}/"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update(self, client, section):
        """Test updating a section"""
        client.force_authenticate(user=section.document.user)
        title = "New Title"
        response = client.patch(
            f"/api/documents/{section.document.pk}/sections/{section.pk}/",
            {"title": title},
        )
        assert response.status_code == status.HTTP_200_OK
        section.refresh_from_db()
        assert section.title == title

    def test_update_bad(self, client, user, section):
        """You may not update a section on a document you do not have edit access to"""
        client.force_authenticate(user=user)
        title = "New Title"
        response = client.patch(
            f"/api/documents/{section.document.pk}/sections/{section.pk}/",
            {"title": title},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_destroy(self, client, section):
        """Test destroying a section"""
        client.force_authenticate(user=section.document.user)
        response = client.delete(
            f"/api/documents/{section.document.pk}/sections/{section.pk}/"
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Section.objects.filter(pk=section.pk).exists()

    def test_destroy_bad(self, client, user, section):
        """You may not destroy a section on a document you do now have edit access to"""
        client.force_authenticate(user=user)
        response = client.delete(
            f"/api/documents/{section.document.pk}/sections/{section.pk}/"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db()
class TestEntityAPI:
    def test_list(self, client, document):
        """List the entities of a document"""
        size = 10
        EntityFactory.create_batch(size, document=document)
        response = client.get(f"/api/documents/{document.pk}/entities/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert len(response_json["results"]) == size


@pytest.mark.django_db()
class TestEntityDateAPI:
    def test_list(self, client, document):
        """List the entitie dates of a document"""
        size = 10
        EntityDateFactory.create_batch(size, document=document)
        response = client.get(f"/api/documents/{document.pk}/dates/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert len(response_json["results"]) == size
