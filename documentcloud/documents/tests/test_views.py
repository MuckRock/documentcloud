# Django
from django.conf import settings
from rest_framework import status

# Standard Library
from unittest.mock import patch

# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.models import Document, DocumentError, Note, Section
from documentcloud.documents.serializers import (
    DocumentSerializer,
    NoteSerializer,
    SectionSerializer,
)
from documentcloud.documents.tests.factories import (
    DocumentErrorFactory,
    DocumentFactory,
    EntityDateFactory,
    EntityFactory,
    NoteFactory,
    SectionFactory,
)
from documentcloud.organizations.serializers import OrganizationSerializer
from documentcloud.users.serializers import UserSerializer
from documentcloud.users.tests.factories import UserFactory


@pytest.mark.django_db()
class TestDocumentAPI:
    def test_list(self, client):
        """List documents"""
        size = 10
        DocumentFactory.create_batch(size)
        response = client.get(f"/api/documents/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["results"]) == size

    def test_list_filter(self, client, user):
        """List a subset of documents"""
        size = 5
        client.force_authenticate(user=user)
        DocumentFactory.create_batch(size)
        DocumentFactory.create_batch(size, user=user)
        response = client.get(f"/api/documents/", {"user": user.pk})
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["results"]) == size

    def test_list_order(self, client):
        """List the documents in order"""
        DocumentFactory(page_count=3)
        DocumentFactory(page_count=1)
        DocumentFactory(page_count=2)
        response = client.get(f"/api/documents/", {"ordering": "page_count"})
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert [j["page_count"] for j in response_json["results"]] == [1, 2, 3]

    def test_list_presigned_url_field(self, client):
        """List documents"""
        DocumentFactory(status=Status.nofile)
        DocumentFactory(status=Status.success)
        response = client.get(f"/api/documents/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        for doc_json in response_json["results"]:
            assert "presigned_url" not in doc_json

    def test_create_file_url(self, client, user):
        """Upload a document with a file and a title"""
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/documents/",
            {"title": "Test", "file_url": "http://www.example.com/test.pdf"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = response.json()
        assert Document.objects.filter(pk=response_json["id"]).exists()
        assert "presigned_url" not in response_json

    def test_create_direct(self, client, user):
        """Create a document and upload the file directly"""
        client.force_authenticate(user=user)
        response = client.post(f"/api/documents/", {"title": "Test"})
        assert response.status_code == status.HTTP_201_CREATED
        response_json = response.json()
        assert Document.objects.filter(pk=response_json["id"]).exists()
        assert "presigned_url" in response_json

    def test_create_bad_no_user(self, client):
        """Must be logged in to create a document"""
        response = client.post(
            f"/api/documents/",
            {"title": "Test", "file_url": "http://www.example.com/test.pdf"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_retrieve(self, client, document):
        """Test retrieving a document"""
        response = client.get(f"/api/documents/{document.pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        serializer = DocumentSerializer(document)
        assert response_json == serializer.data
        assert response_json["access"] == "public"
        assert "presigned_url" not in response_json

    def test_retrieve_no_file(self, client):
        """Test retrieving a document with a presigned url"""
        document = DocumentFactory(status=Status.nofile)
        client.force_authenticate(user=document.user)
        response = client.get(f"/api/documents/{document.pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert "presigned_url" in response_json

    def test_retrieve_no_file_shared(self, client):
        """Test retrieving a shared document without a file"""
        document = DocumentFactory(status=Status.nofile, access=Access.organization)
        user = UserFactory(organizations=[document.organization])
        client.force_authenticate(user=user)
        response = client.get(f"/api/documents/{document.pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert "presigned_url" not in response_json

    def test_retrieve_expand(self, client, document):
        """Test retrieving a document with an expanded user and organization"""
        response = client.get(
            f"/api/documents/{document.pk}/", {"expand": "user,organization"}
        )
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        user_serializer = UserSerializer(document.user)
        organization_serializer = OrganizationSerializer(document.organization)
        assert response_json["user"] == user_serializer.data
        assert response_json["organization"] == organization_serializer.data

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

    def test_bulk_update(self, client, user):
        """Test updating multiple documents"""
        client.force_authenticate(user=user)
        documents = DocumentFactory.create_batch(2, user=user, access=Access.private)
        response = client.patch(
            f"/api/documents/",
            [
                {"id": documents[0].pk, "access": "public"},
                {"id": documents[1].pk, "access": "public"},
            ],
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        for document in documents:
            document.refresh_from_db()
            assert document.access == Access.public

    def test_bulk_update_bad(self, client, user):
        """Test updating multiple documents, without permissions for all"""
        client.force_authenticate(user=user)
        good_document = DocumentFactory(user=user, access=Access.public)
        bad_document = DocumentFactory(access=Access.public)
        response = client.patch(
            f"/api/documents/",
            [
                {"id": good_document.pk, "access": "private"},
                {"id": bad_document.pk, "access": "private"},
            ],
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        good_document.refresh_from_db()
        assert good_document.access == Access.public
        bad_document.refresh_from_db()
        assert bad_document.access == Access.public

    def test_bulk_update_missing(self, client, user):
        """Test updating multiple documents, with some missing"""
        client.force_authenticate(user=user)
        document = DocumentFactory(user=user, access=Access.private)
        response = client.patch(
            f"/api/documents/",
            [{"id": document.pk, "access": "public"}, {"id": 1234, "access": "public"}],
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        document.refresh_from_db()
        assert document.access == Access.private
        assert not Document.objects.filter(pk=1234).exists()

    def test_destroy(self, client, document):
        """Test destroying a document"""
        client.force_authenticate(user=document.user)
        response = client.delete(f"/api/documents/{document.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        document.refresh_from_db()
        assert document.status == Status.deleted

    def test_bulk_destroy(self, client, user):
        """Test deleting multiple documents"""
        client.force_authenticate(user=user)
        documents = DocumentFactory.create_batch(4, user=user)
        response = client.delete(
            "/api/documents/?id__in={}".format(
                ",".join(str(d.pk) for d in documents[:2])
            )
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
        # make sure only first 2 were deleted
        for document in documents[:2]:
            document.refresh_from_db()
            assert document.status == Status.deleted
        for document in documents[2:]:
            document.refresh_from_db()
            assert document.status != Status.deleted

    def test_bulk_destroy_no_filter(self, client, user):
        """May not delete *all* the documents"""
        client.force_authenticate(user=user)
        documents = DocumentFactory.create_batch(2, user=user)
        response = client.delete(f"/api/documents/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        for document in documents:
            document.refresh_from_db()
            assert document.status != Status.deleted

    def test_bulk_destroy_bad(self, client, user):
        """Test deleting multiple documents without permission"""
        client.force_authenticate(user=user)
        good_document = DocumentFactory(user=user, access=Access.public)
        bad_document = DocumentFactory(access=Access.public)
        response = client.delete(
            f"/api/documents/?id__in={good_document.pk},{bad_document.pk}"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        good_document.refresh_from_db()
        assert good_document.status != Status.deleted
        bad_document.refresh_from_db()
        assert bad_document.status != Status.deleted


@pytest.mark.django_db()
class TestDocumentErrorAPI:
    def test_list(self, client, document):
        """List the errors of a document"""
        size = 10
        DocumentErrorFactory.create_batch(size, document=document)
        response = client.get(f"/api/documents/{document.pk}/errors/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["results"]) == size

    def test_create(self, client, document):
        """Create an error"""
        response = client.post(
            f"/api/documents/{document.pk}/errors/",
            {"message": "An error has occurred"},
            HTTP_AUTHORIZATION=f"processing-token {settings.PROCESSING_TOKEN}",
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = response.json()
        assert DocumentError.objects.filter(pk=response_json["id"]).exists()

    def test_create_bad(self, client, document):
        """Only the processing functions my create errors"""
        client.force_authenticate(user=document.user)
        response = client.post(
            f"/api/documents/{document.pk}/errors/",
            {"message": "An error has occurred"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db()
class TestNoteAPI:
    def test_list(self, client, document):
        """List the notes of a document"""
        size = 10
        NoteFactory.create_batch(size, document=document)
        response = client.get(f"/api/documents/{document.pk}/notes/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
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
        response_json = response.json()
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
        response_json = response.json()
        assert Note.objects.filter(pk=response_json["id"]).exists()

    def test_retrieve(self, client, note):
        """Test retrieving a note"""

        response = client.get(f"/api/documents/{note.document.pk}/notes/{note.pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
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
        response_json = response.json()
        assert len(response_json["results"]) == size

    def test_create(self, client, document):
        """Create a section"""
        client.force_authenticate(user=document.user)
        response = client.post(
            f"/api/documents/{document.pk}/sections/",
            {"title": "Test", "page_number": 1},
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = response.json()
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
        response_json = response.json()
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
        response_json = response.json()
        assert len(response_json["results"]) == size


@pytest.mark.django_db()
class TestEntityDateAPI:
    def test_list(self, client, document):
        """List the entitie dates of a document"""
        size = 10
        EntityDateFactory.create_batch(size, document=document)
        response = client.get(f"/api/documents/{document.pk}/dates/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["results"]) == size


@pytest.mark.django_db()
class TestDataAPI:
    def test_list(self, client):
        """List the data for a document"""
        document = DocumentFactory(data={"color": ["red", "blue"], "state": ["ma"]})
        response = client.get(f"/api/documents/{document.pk}/data/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == document.data

    def test_list_bad(self, client):
        """List the data for a document you cannot view"""
        document = DocumentFactory(
            access=Access.private, data={"color": ["red", "blue"], "state": ["ma"]}
        )
        response = client.get(f"/api/documents/{document.pk}/data/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve(self, client):
        """List the values for a key"""
        document = DocumentFactory(data={"color": ["red", "blue"], "state": ["ma"]})
        response = client.get(f"/api/documents/{document.pk}/data/color/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == document.data["color"]

    def test_update(self, client, document):
        """Add a new key value pair to a document"""
        client.force_authenticate(user=document.user)
        response = client.put(
            f"/api/documents/{document.pk}/data/color/",
            {"values": ["red"]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.data == {"color": ["red"]}

    def test_update_existing(self, client):
        """Overwrite a key value pair to a document"""
        document = DocumentFactory(data={"color": ["red", "blue"], "state": ["ma"]})
        client.force_authenticate(user=document.user)
        response = client.put(
            f"/api/documents/{document.pk}/data/color/",
            {"values": ["green", "yellow"]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.data == {"color": ["green", "yellow"], "state": ["ma"]}

    def test_update_bad(self, client, document, user):
        """Add a new key value pair to a document for a document you cannot edit"""
        client.force_authenticate(user=user)
        response = client.put(
            f"/api/documents/{document.pk}/data/color/",
            {"values": ["red"]},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_partial_update(self, client):
        """Add a new value to an existing key"""
        document = DocumentFactory(data={"color": ["red", "blue"], "state": ["ma"]})
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/documents/{document.pk}/data/state/",
            {"values": ["nj"]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.data["state"] == ["ma", "nj"]

    def test_partial_update_new(self, client, document):
        """Add a new value to non existing key"""
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/documents/{document.pk}/data/state/",
            {"values": ["nj", "ca"]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.data["state"] == ["nj", "ca"]

    def test_partial_update_remove(self, client):
        """Remove a value from an existing key"""
        document = DocumentFactory(data={"color": ["red", "blue"], "state": ["ma"]})
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/documents/{document.pk}/data/color/",
            {"remove": ["red"]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.data["color"] == ["blue"]

    def test_partial_update_add_remove(self, client):
        """Add and remove values from an existing key"""
        document = DocumentFactory(data={"color": ["red", "blue"], "state": ["ma"]})
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/documents/{document.pk}/data/color/",
            {"values": ["green"], "remove": ["red"]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.data["color"] == ["blue", "green"]

    def test_partial_update_remove_all(self, client):
        """Removing all values removes the key"""
        document = DocumentFactory(data={"color": ["red", "blue"], "state": ["ma"]})
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/documents/{document.pk}/data/color/",
            {"remove": ["red", "blue"]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert "color" not in document.data

    def test_destroy(self, client):
        """Remove a key"""
        document = DocumentFactory(data={"color": ["red", "blue"], "state": ["ma"]})
        client.force_authenticate(user=document.user)
        response = client.delete(f"/api/documents/{document.pk}/data/state/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        document.refresh_from_db()
        assert document.data == {"color": ["red", "blue"]}


@pytest.mark.django_db()
class TestRedactionAPI:
    def test_create(self, client, mocker):
        """Create multiple redactions"""
        mock_redact = mocker.patch("documentcloud.documents.views.redact")
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=document.user)
        data = [
            {"y1": 0.1, "x1": 0.1, "x2": 0.2, "y2": 0.2, "page": 0},
            {"y1": 0.3, "x1": 0.3, "x2": 0.4, "y2": 0.4, "page": 1},
        ]
        response = client.post(
            f"/api/documents/{document.pk}/redactions/", data, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        mock_redact.delay.assert_called_once_with(document.pk, document.slug, data)

    def test_create_anonymous(self, client):
        """You cannot create redactions if you are not logged in"""
        document = DocumentFactory(page_count=2)
        data = [
            {"top": 10, "left": 10, "bottom": 20, "right": 20, "page": 0},
            {"top": 30, "left": 30, "bottom": 40, "right": 40, "page": 1},
        ]
        response = client.post(
            f"/api/documents/{document.pk}/redactions/", data, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_no_view(self, client, user):
        """You cannot create redactions on documents you cannot view"""
        document = DocumentFactory(page_count=2, access=Access.private)
        client.force_authenticate(user=user)
        data = [
            {"top": 10, "left": 10, "bottom": 20, "right": 20, "page": 0},
            {"top": 30, "left": 30, "bottom": 40, "right": 40, "page": 1},
        ]
        response = client.post(
            f"/api/documents/{document.pk}/redactions/", data, format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_no_edit(self, client, user):
        """You cannot create redactions on documents you cannot edit"""
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=user)
        data = [
            {"top": 10, "left": 10, "bottom": 20, "right": 20, "page": 0},
            {"top": 30, "left": 30, "bottom": 40, "right": 40, "page": 1},
        ]
        response = client.post(
            f"/api/documents/{document.pk}/redactions/", data, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_bad_page(self, client):
        """You cannot create redactions on pages that don't exist"""
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=document.user)
        data = [
            {"top": 10, "left": 10, "bottom": 20, "right": 20, "page": 0},
            {"top": 30, "left": 30, "bottom": 40, "right": 40, "page": 2},
        ]
        response = client.post(
            f"/api/documents/{document.pk}/redactions/", data, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_bad_shape(self, client):
        """You cannot create redactions with bad dimensions"""
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=document.user)
        data = [
            {"top": 30, "left": 10, "bottom": 20, "right": 20, "page": 0},
            {"top": 30, "left": 50, "bottom": 40, "right": 40, "page": 1},
        ]
        response = client.post(
            f"/api/documents/{document.pk}/redactions/", data, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
