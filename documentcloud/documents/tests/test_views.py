# Django
from django.conf import settings
from django.db import connection, reset_queries
from django.test.utils import override_settings
from rest_framework import status

# Third Party
import pytest

# DocumentCloud
from documentcloud.core.tests import run_commit_hooks
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
    EntityOccurrenceFactory,
    LegacyEntityFactory,
    NoteFactory,
    SectionFactory,
)
from documentcloud.organizations.serializers import OrganizationSerializer
from documentcloud.organizations.tests.factories import ProfessionalOrganizationFactory
from documentcloud.projects.models import ProjectMembership
from documentcloud.projects.tests.factories import ProjectFactory
from documentcloud.users.serializers import UserSerializer
from documentcloud.users.tests.factories import UserFactory

# pylint: disable=too-many-lines, too-many-public-methods


@pytest.mark.django_db()
class TestFreestandingEntityAPI:
    def test_create_freestanding_entity(self, client, document, user, mocker):
        # """Create freestanding entities"""
        entity_body = {
            "name": "Dog",
            "kind": "unknown",
            "metadata": {"wikipedia_url": "https://en.wikipedia.org/wiki/Dog"},
        }
        _get_or_create_entities = mocker.patch(
            "documentcloud.documents.entity_extraction._get_or_create_entities",
            return_value={"mock_mid": entity_body},
        )

        client.force_authenticate(user=user)
        response = client.post(
            "/api/freestanding_entities/",
            entity_body,
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert (
            response.content
            == b'{"name":"Dog","kind":"unknown","metadata":{"wikipedia_url":"https://en.wikipedia.org/wiki/Dog"}}' # pylint: disable=line-too-long
        )
        _get_or_create_entities.assert_called_once_with([entity_body])


@pytest.mark.django_db()
class TestDocumentAPI:
    def test_list(self, client):
        """List documents"""
        size = 10
        DocumentFactory.create_batch(size)
        response = client.get("/api/documents/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["results"]) == size
        # document list should never be cached
        assert "no-cache" in response["Cache-Control"]
        assert "public" not in response["Cache-Control"]
        assert "max-age" not in response["Cache-Control"]

    def test_list_filter_user(self, client, user):
        """List a subset of documents"""
        size = 5
        client.force_authenticate(user=user)
        DocumentFactory.create_batch(size)
        DocumentFactory.create_batch(size, user=user)
        response = client.get("/api/documents/", {"user": user.pk})
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["results"]) == size

    def test_list_filter_status(self, client, user):
        """List a subset of documents"""
        size = 5
        client.force_authenticate(user=user)
        DocumentFactory.create_batch(size, user=user, status=Status.success)
        DocumentFactory.create_batch(size, user=user, status=Status.error)
        response = client.get("/api/documents/", {"status": "success"})
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["results"]) == size

    def test_list_filter_multi_status(self, client, user):
        """List a subset of documents from multiple statuses"""
        size = 5
        client.force_authenticate(user=user)
        DocumentFactory.create_batch(size, user=user, status=Status.success)
        DocumentFactory.create_batch(size, user=user, status=Status.pending)
        DocumentFactory.create_batch(size, user=user, status=Status.error)

        response = client.get("/api/documents/", {"status": ["success", "pending"]})
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["results"]) == 2 * size

        response = client.get("/api/documents/", {"status": "success,pending"})
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["results"]) == 2 * size

    def test_list_filter_bad_status(self, client, user):
        """Error if give bad value for status"""
        size = 5
        client.force_authenticate(user=user)
        DocumentFactory.create_batch(size, user=user, status=Status.success)
        DocumentFactory.create_batch(size, user=user, status=Status.error)
        response = client.get("/api/documents/", {"status": "good"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_presigned_url_field(self, client):
        """List documents"""
        DocumentFactory(status=Status.nofile)
        DocumentFactory(status=Status.success)
        response = client.get("/api/documents/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        for doc_json in response_json["results"]:
            assert "presigned_url" not in doc_json

    @pytest.mark.parametrize(
        "expand", ["", "~all", ("user.organization,organization,projects,sections")]
    )
    @override_settings(DEBUG=True)
    def test_list_queries(self, client, expand):
        """Queries should be constant"""
        small_size = 1
        documents = DocumentFactory.create_batch(small_size)
        ProjectFactory.create_batch(small_size, documents=documents)
        for document in documents:
            NoteFactory.create_batch(small_size, document=document)
            SectionFactory.create_batch(small_size, document=document)
        reset_queries()
        client.get(f"/api/documents/?expand={expand}")
        num_queries = len(connection.queries)

        size = 10
        documents = DocumentFactory.create_batch(size)
        ProjectFactory.create_batch(size, documents=documents)
        for document in documents:
            NoteFactory.create_batch(size, document=document)
            SectionFactory.create_batch(size, document=document)
        reset_queries()
        response = client.get(f"/api/documents/?expand={expand}")
        assert num_queries == len(connection.queries)
        assert len(response.json()["results"]) == size + small_size

    def test_create_file_url(self, client, user):
        """Upload a document with a file and a title"""
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/",
            {"title": "Test", "file_url": "http://www.example.com/test.pdf"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = response.json()
        assert Document.objects.filter(pk=response_json["id"]).exists()
        assert "presigned_url" not in response_json

    def test_create_file_url_bad_ocr_engine(self, client, user):
        """Non-premium user cannot set ocr engine to textract"""
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/",
            {
                "title": "Test",
                "file_url": "http://www.example.com/test.pdf",
                "ocr_engine": "textract",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_file_url_good_ocr_engine(self, client, user):
        """Non-premium user can set ocr engine to tess4"""
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/",
            {
                "title": "Test",
                "file_url": "http://www.example.com/test.pdf",
                "ocr_engine": "tess4",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = response.json()
        assert Document.objects.filter(pk=response_json["id"]).exists()

    def test_create_file_url_bad_ocr_engine_language(self, client):
        """Textract can only be used with supported languages"""
        org = ProfessionalOrganizationFactory()
        user = UserFactory(organizations=[org])
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/",
            {
                "title": "Test",
                "file_url": "http://www.example.com/test.pdf",
                "ocr_engine": "textract",
                "language": "ara",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_direct(self, client, user):
        """Create a document and upload the file directly"""
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/",
            {"title": "Test", "data": {"tag": ["good"]}},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = response.json()
        assert Document.objects.filter(pk=response_json["id"]).exists()
        assert "presigned_url" in response_json

    def test_create_project(self, client, project):
        """Create a document in a project"""
        client.force_authenticate(user=project.user)
        response = client.post(
            "/api/documents/",
            {"title": "Test", "projects": [project.pk]},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = response.json()
        assert ProjectMembership.objects.filter(
            document_id=response_json["id"], project=project, edit_access=True
        ).exists()

    def test_create_public(self, client, user):
        """Create a public document when you are a verified journalist"""
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/", {"title": "Test", "access": "public"}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_bad_no_user(self, client):
        """Must be logged in to create a document"""
        response = client.post(
            "/api/documents/",
            {"title": "Test", "file_url": "http://www.example.com/test.pdf"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_bad_id(self, client, user):
        """Create a document and set an ID"""
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/", {"title": "Test", "id": 999}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["id"] != 999

    def test_create_bad_public(self, client):
        """Create a document when you are not a verified journalist"""
        user = UserFactory(membership__organization__verified_journalist=False)
        client.force_authenticate(user=user)
        response = client.post("/api/documents/", {"title": "Test"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_bad_data(self, client, user):
        """Data keys must be alphanumeric"""
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/",
            {"title": "Test", "data": {"bad key?": ["foo"]}},
            format="json",
        )
        # this check is currently disabled
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_bad_ocr_engine(self, client, user):
        """OCR engine may only be set if file_url is set"""
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/",
            {"title": "Test", "ocr_engine": "tess4"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_create(self, client, user, django_assert_num_queries):
        """Create multiple documents"""
        client.force_authenticate(user=user)
        with django_assert_num_queries(9):
            response = client.post(
                "/api/documents/",
                [{"title": "Test 1"}, {"title": "Test 2"}, {"title": "Test 3"}],
                format="json",
            )
        assert response.status_code == status.HTTP_201_CREATED
        assert (
            Document.objects.filter(pk__in=[d["id"] for d in response.json()]).count()
            == 3
        )

    def test_bulk_create_excess(self, client, user):
        """Attempt to create too many documents"""
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/",
            [{"title": f"Test {i}"} for i in range(settings.REST_BULK_LIMIT + 1)],
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_retrieve(self, client, document):
        """Test retrieving a document"""
        response = client.get(f"/api/documents/{document.pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        serializer = DocumentSerializer(document)
        assert response_json == serializer.data
        assert response_json["access"] == "public"
        assert "presigned_url" not in response_json
        # public document retrieves should be cached
        assert "public" in response["Cache-Control"]
        assert f"max-age={settings.CACHE_CONTROL_MAX_AGE}" in response["Cache-Control"]
        assert "private" not in response["Cache-Control"]
        assert "no-cache" not in response["Cache-Control"]

    def test_retrieve_auth(self, client, document):
        """Test retrieving a document"""
        client.force_authenticate(user=document.user)
        response = client.get(f"/api/documents/{document.pk}/")
        assert response.status_code == status.HTTP_200_OK
        # authenticated document retrieves should not be cached
        assert "private" in response["Cache-Control"]
        assert "no-cache" in response["Cache-Control"]
        assert "public" not in response["Cache-Control"]
        assert "max-age" not in response["Cache-Control"]

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
        """Test retrieving a document with an expanded fields"""
        public_note = NoteFactory.create(document=document, access=Access.public)
        private_note = NoteFactory.create(document=document, access=Access.private)
        response = client.get(
            f"/api/documents/{document.pk}/", {"expand": "user,organization,notes"}
        )
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        user_serializer = UserSerializer(document.user)
        organization_serializer = OrganizationSerializer(document.organization)
        public_note_serializer = NoteSerializer(public_note)
        private_note_serializer = NoteSerializer(private_note)
        assert response_json["user"] == user_serializer.data
        assert response_json["organization"] == organization_serializer.data
        assert public_note_serializer.data in response_json["notes"]
        assert private_note_serializer.data not in response_json["notes"]

    def test_retrieve_expand_note_collab(self, client, user):
        """Test retrieving a document with notes"""
        document = DocumentFactory(access=Access.private)
        NoteFactory.create(document=document, access=Access.organization)
        ProjectFactory(edit_documents=[document], edit_collaborators=[user])
        client.force_authenticate(user=user)
        response = client.get(f"/api/documents/{document.pk}/", {"expand": "notes"})
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["notes"]) == 1

    def test_retrieve_expand_note_no_collab(self, client, user):
        """Test retrieving a document with notes"""
        document = DocumentFactory(access=Access.private)
        NoteFactory.create(document=document, access=Access.organization)
        ProjectFactory(edit_documents=[document], collaborators=[user])
        client.force_authenticate(user=user)
        response = client.get(f"/api/documents/{document.pk}/", {"expand": "notes"})
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["notes"]) == 0

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

    def test_update_public(self, client, document):
        """Test updating a document to public when you are a verified journalist"""
        client.force_authenticate(user=document.user)
        response = client.patch(f"/api/documents/{document.pk}/", {"access": "public"})
        assert response.status_code == status.HTTP_200_OK

    def test_update_bad_public(self, client):
        """Test updating a document to public when you are not a verified journalist"""
        document = DocumentFactory(
            user__membership__organization__verified_journalist=False
        )
        client.force_authenticate(user=document.user)
        response = client.patch(f"/api/documents/{document.pk}/", {"access": "public"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_bad_file_url(self, client, document):
        """You may not update the file url"""
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/documents/{document.pk}/",
            {"file_url": "https://www.example.com/2.pdf"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_bad_ocr_engine(self, client, document):
        """You may not update the ocr_engine"""
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/documents/{document.pk}/",
            {"ocr_engine": "textract"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_bad_access(self, client, document):
        """You may not make a document invisible"""
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/documents/{document.pk}/", {"access": "invisible"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_bad_access_processing(self, client):
        """You may not update the access of a processing document"""
        document = DocumentFactory(status=Status.readable, access=Access.public)
        client.force_authenticate(user=document.user)
        response = client.patch(f"/api/documents/{document.pk}/", {"access": "private"})
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

    def test_update_bad_project(self, client, document):
        """Update a documents project using the project membership API only"""
        project = ProjectFactory(user=document.user)
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/documents/{document.pk}/", {"projects": [project.pk]}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_bad_id(self, client, document):
        """You may not update the id"""
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/documents/{document.pk}/", {"id": document.pk + 1}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["id"] == document.pk
        assert Document.objects.count() == 1

    def test_update_data(self, client, document):
        """Test updating a document's data directly"""
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/documents/{document.pk}/",
            {"data": {"color": ["blue"]}},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.data["color"] == ["blue"]

    def test_update_data_long(self, client, document):
        """Test updating a document's data directly with a value that is too long"""
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/documents/{document.pk}/",
            {"data": {"color": ["a" * 301]}},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_owner(self, client, document, user, organization):
        """Test updating a document's owner"""
        organization.users.add(document.user, user)
        client.force_authenticate(user=document.user)
        response = client.patch(f"/api/documents/{document.pk}/", {"user": user.pk})
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.user == user

    def test_update_owner_bad_new(self, client, document, user):
        """Test updating a document's owner"""
        client.force_authenticate(user=document.user)
        response = client.patch(f"/api/documents/{document.pk}/", {"user": user.pk})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        document.refresh_from_db()
        assert document.user != user

    def test_update_owner_bad_old(self, client, document, user):
        """Test updating a document's owner"""
        client.force_authenticate(user=user)
        response = client.patch(f"/api/documents/{document.pk}/", {"user": user.pk})
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.user != user

    def test_update_owner_bad_steal(self, client, document, user, organization):
        """Test updating a document's owner"""
        document.access = Access.organization
        document.organization = organization
        document.save()
        organization.users.add(document.user, user)
        client.force_authenticate(user=user)
        response = client.patch(f"/api/documents/{document.pk}/", {"user": user.pk})
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.user != user

    def test_bulk_update(self, client, user):
        """Test updating multiple documents"""
        client.force_authenticate(user=user)
        documents = DocumentFactory.create_batch(3, user=user, access=Access.private)
        response = client.patch(
            "/api/documents/",
            [{"id": d.pk, "source": "Daily Planet"} for d in documents[:2]],
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert Document.objects.filter(source="Daily Planet").count() == 2

    def test_bulk_update_bad(self, client, user):
        """Test updating multiple documents, without permissions for all"""
        client.force_authenticate(user=user)
        good_document = DocumentFactory(user=user, access=Access.public)
        bad_document = DocumentFactory(access=Access.public)
        response = client.patch(
            "/api/documents/",
            [
                {"id": good_document.pk, "access": "private"},
                {"id": bad_document.pk, "access": "private"},
            ],
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        good_document.refresh_from_db()
        assert good_document.access == Access.public
        bad_document.refresh_from_db()
        assert bad_document.access == Access.public

    def test_bulk_update_missing(self, client, user):
        """Test updating multiple documents, with some missing"""
        client.force_authenticate(user=user)
        document = DocumentFactory(user=user, access=Access.private)
        response = client.patch(
            "/api/documents/",
            [{"id": document.pk, "access": "public"}, {"id": 1234, "access": "public"}],
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        document.refresh_from_db()
        assert document.access == Access.private
        assert not Document.objects.filter(pk=1234).exists()

    def test_bulk_update_excess(self, client, user):
        """Attempt to update too many documents"""
        client.force_authenticate(user=user)
        num = settings.REST_BULK_LIMIT + 1
        documents = DocumentFactory.create_batch(num, user=user, access=Access.private)
        response = client.patch(
            "/api/documents/",
            [{"id": document.pk, "access": "public"} for document in documents],
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_update_access(self, client, user):
        """Test updating multiple documents access"""
        client.force_authenticate(user=user)
        documents = DocumentFactory.create_batch(3, user=user, access=Access.public)
        # make sure a processing document doesn't block other documents
        DocumentFactory(user=user, status=Status.readable)
        response = client.patch(
            "/api/documents/",
            [{"id": d.pk, "access": "private"} for d in documents],
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        for document in documents:
            document.refresh_from_db()
            assert document.access == Access.private

    def test_bulk_update_access_bad(self, client, user):
        """Test updating multiple documents access"""
        client.force_authenticate(user=user)
        documents = DocumentFactory.create_batch(
            3, user=user, access=Access.private, status=Status.pending
        )
        response = client.patch(
            "/api/documents/",
            [{"id": d.pk, "access": "public"} for d in documents],
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_update_bad_id(self, client, user):
        """Test updating multiple documents, with bad ID"""
        client.force_authenticate(user=user)
        response = client.patch(
            "/api/documents/", [{"id": "a", "access": "private"}], format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_update_missing_id(self, client, user):
        """Test updating multiple documents, with missing IDs"""
        client.force_authenticate(user=user)
        response = client.patch(
            "/api/documents/", [{"access": "private"}], format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_update_owner(self, client, user, organization):
        """Test updating a document's owner"""
        my_document = DocumentFactory(
            user=user, organization=organization, access=Access.organization
        )
        other_document = DocumentFactory(
            organization=organization, access=Access.organization
        )
        organization.users.add(other_document.user, user)
        client.force_authenticate(user=user)
        response = client.patch(
            "/api/documents/",
            [{"id": my_document.pk, "user": other_document.user.pk}],
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        my_document.refresh_from_db()
        assert my_document.user == other_document.user

    def test_bulk_update_perm_queries(self, client, user, django_assert_num_queries):
        """Test bulk update queries for permission checking"""
        documents = DocumentFactory.create_batch(10, user=user, access=Access.public)
        client.force_authenticate(user=user)
        with django_assert_num_queries(13):
            response = client.patch(
                "/api/documents/",
                [{"id": d.pk, "source": "My source"} for d in documents],
                format="json",
            )
        assert response.status_code == status.HTTP_200_OK

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
        doc_ids = ",".join(str(d.pk) for d in documents[:2])
        response = client.delete(f"/api/documents/?id__in={doc_ids}")
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
        response = client.delete("/api/documents/")
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
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        good_document.refresh_from_db()
        assert good_document.status != Status.deleted
        bad_document.refresh_from_db()
        assert bad_document.status != Status.deleted

    def test_bulk_destroy_excess(self, client, user):
        """Attempt to delete too many documents"""
        client.force_authenticate(user=user)
        num = settings.REST_BULK_LIMIT + 1
        documents = DocumentFactory.create_batch(num, user=user)
        doc_ids = ",".join(str(d.pk) for d in documents)
        response = client.delete(f"/api/documents/?id__in={doc_ids}")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_process(self, client, document, mocker):
        """Test processing a document"""
        # pretend the file exists
        mocker.patch(
            "documentcloud.common.environment.storage.exists", return_value=True
        )
        client.force_authenticate(user=document.user)
        response = client.post(f"/api/documents/{document.pk}/process/")
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.status == Status.pending

    def test_process_force_ocr(self, client, document, mocker):
        """Test processing a document and force ocr"""
        # pretend the file exists
        mocker.patch(
            "documentcloud.common.environment.storage.exists", return_value=True
        )
        client.force_authenticate(user=document.user)
        response = client.post(
            f"/api/documents/{document.pk}/process/", {"force_ocr": True}
        )
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.status == Status.pending

    def test_process_ocr_engine_free(self, client, document, mocker):
        """Must have a paid account to use Textract"""
        # pretend the file exists
        mocker.patch(
            "documentcloud.common.environment.storage.exists", return_value=True
        )
        client.force_authenticate(user=document.user)
        response = client.post(
            f"/api/documents/{document.pk}/process/", {"ocr_engine": "textract"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_process_ocr_engine(self, client, mocker):
        """Test setting ocr_engine"""
        org = ProfessionalOrganizationFactory()
        user = UserFactory(organizations=[org])
        document = DocumentFactory(user=user)
        # pretend the file exists
        mocker.patch(
            "documentcloud.common.environment.storage.exists", return_value=True
        )
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/documents/{document.pk}/process/", {"ocr_engine": "textract"}
        )
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.status == Status.pending

    def test_process_ocr_engine_bad_lang(self, client, mocker):
        """Textract does not support all languages"""
        org = ProfessionalOrganizationFactory()
        user = UserFactory(organizations=[org])
        document = DocumentFactory(user=user, language="ara")
        # pretend the file exists
        mocker.patch(
            "documentcloud.common.environment.storage.exists", return_value=True
        )
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/documents/{document.pk}/process/",
            {"ocr_engine": "textract"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_process_bad(self, client, user, document, mocker):
        """Test processing a document you do not have edit permissions to"""
        # pretend the file exists
        mocker.patch(
            "documentcloud.common.environment.storage.exists", return_value=True
        )
        client.force_authenticate(user=user)
        response = client.post(f"/api/documents/{document.pk}/process/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_process_bad_status(self, client, mocker):
        """Test processing a document thats already processing"""
        document = DocumentFactory(status=Status.pending)
        # pretend the file exists
        mocker.patch(
            "documentcloud.common.environment.storage.exists", return_value=True
        )
        client.force_authenticate(user=document.user)
        response = client.post(f"/api/documents/{document.pk}/process/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_process(self, client, user, mocker, django_assert_num_queries):
        """Test processing multiple documents"""
        # pretend the files exists
        mocker.patch(
            "documentcloud.common.environment.storage.exists", return_value=True
        )
        documents = DocumentFactory.create_batch(2, user=user)
        client.force_authenticate(user=user)
        with django_assert_num_queries(8):
            response = client.post(
                "/api/documents/process/",
                [{"id": d.pk} for d in documents],
                format="json",
            )
        assert response.status_code == status.HTTP_200_OK
        for document in documents:
            document.refresh_from_db()
            assert document.status == Status.pending

    def test_bulk_process_ocr_engine(self, client, mocker):
        """Test processing multiple documents with textract"""
        org = ProfessionalOrganizationFactory()
        user = UserFactory(organizations=[org])
        # pretend the files exists
        mocker.patch(
            "documentcloud.common.environment.storage.exists", return_value=True
        )
        documents = DocumentFactory.create_batch(2, user=user)
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/process/",
            [{"id": d.pk, "ocr_engine": "textract"} for d in documents],
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        for document in documents:
            document.refresh_from_db()
            assert document.status == Status.pending

    def test_bulk_process_old_format(self, client, user, mocker):
        """Test processing multiple documents using old data format"""
        # pretend the files exists
        mocker.patch(
            "documentcloud.common.environment.storage.exists", return_value=True
        )
        documents = DocumentFactory.create_batch(2, user=user)
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/process/", {"ids": [d.pk for d in documents]}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        for document in documents:
            document.refresh_from_db()
            assert document.status == Status.pending

    def test_bulk_process_force_ocr(self, client, user, mocker):
        """Test processing multiple documents, force some OCR"""
        # pretend the files exists
        mocker.patch(
            "documentcloud.common.environment.storage.exists", return_value=True
        )
        documents = DocumentFactory.create_batch(2, user=user)
        force_ocrs = [False, True]
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/process/",
            [{"id": d.pk, "force_ocr": f} for (d, f) in zip(documents, force_ocrs)],
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        for document in documents:
            document.refresh_from_db()
            assert document.status == Status.pending

    def test_bulk_process_no_data(self, client, user, mocker):
        """Test processing multiple documents without specifying the documents"""
        mocker.patch("documentcloud.documents.views.process")
        # pretend the files exists
        mocker.patch(
            "documentcloud.common.environment.storage.exists", return_value=True
        )
        client.force_authenticate(user=user)
        response = client.post("/api/documents/process/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_process_no_id(self, client, user):
        """Test processing multiple documents with missing IDs"""
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/process/", [{"force_ocr": True}], format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_process_bad(self, client, user, mocker):
        """Test processing multiple documents without permission"""
        mocker.patch("documentcloud.documents.views.process")
        # pretend the files exists
        mocker.patch(
            "documentcloud.common.environment.storage.exists", return_value=True
        )
        good_document = DocumentFactory(user=user, access=Access.public)
        bad_document = DocumentFactory(access=Access.public)
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/process/",
            [{"id": good_document.pk}, {"id": bad_document.pk}],
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_process_bad_ids(self, client, user):
        """Test processing multiple non existent documents"""
        documents = DocumentFactory.create_batch(2, user=user)
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/process/",
            [{"id": d.pk} for d in documents] + [{"id": 9999}],
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_process_excess(self, client, user, mocker):
        """Test processing too many multiple documents"""
        # pretend the file exists
        mocker.patch(
            "documentcloud.common.environment.storage.exists", return_value=True
        )
        num = settings.REST_BULK_LIMIT + 1
        documents = DocumentFactory.create_batch(num, user=user)
        client.force_authenticate(user=user)
        response = client.post(
            "/api/documents/process/", [{"id": d.pk} for d in documents], format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_noindex(self, client, document):
        """Test updating a document to be unindexed"""
        client.force_authenticate(user=document.user)
        response = client.patch(f"/api/documents/{document.pk}/", {"noindex": True})
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert document.noindex

    def test_update_unnoindex(self, client, document):
        """Test updating a document to be unindexed"""
        client.force_authenticate(user=document.user)
        response = client.patch(f"/api/documents/{document.pk}/", {"noindex": False})
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert not document.noindex


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

    @pytest.mark.parametrize("expand", ["", "~all", "user.organization,organization"])
    @override_settings(DEBUG=True)
    def test_list_queries(self, client, document, expand):
        """Queries should be constant"""
        small_size = 1
        NoteFactory.create_batch(small_size, document=document)
        reset_queries()
        client.get(f"/api/documents/{document.pk}/notes/?expand={expand}")
        num_queries = len(connection.queries)

        size = 10
        NoteFactory.create_batch(size, document=document)
        reset_queries()
        response = client.get(f"/api/documents/{document.pk}/notes/?expand={expand}")
        assert num_queries == len(connection.queries)
        assert len(response.json()["results"]) == size + small_size

    def test_create_public(self, client):
        """Create a public note"""
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=document.user)
        response = client.post(
            f"/api/documents/{document.pk}/notes/",
            {
                "title": "Test",
                "content": "Lorem Ipsum",
                "page_number": 1,
                "x1": 0.1,
                "x2": 0.2,
                "y1": 0.3,
                "y2": 0.4,
                "access": "public",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = response.json()
        assert Note.objects.filter(pk=response_json["id"]).exists()

    def test_create_public_bad(self, client, user):
        """You may only create public notes on documents you can edit"""
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/documents/{document.pk}/notes/",
            {
                "title": "Test",
                "content": "Lorem Ipsum",
                "page_number": 1,
                "x1": 0.1,
                "x2": 0.2,
                "y1": 0.3,
                "y2": 0.4,
                "access": "public",
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_page_note(self, client):
        """Create a page level note"""
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=document.user)
        response = client.post(
            f"/api/documents/{document.pk}/notes/",
            {
                "title": "Test",
                "content": "Lorem Ipsum",
                "page_number": 1,
                "access": "public",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_page_note2(self, client):
        """Create a page level note"""
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=document.user)
        response = client.post(
            f"/api/documents/{document.pk}/notes/",
            {
                "title": "Test",
                "content": "Lorem Ipsum",
                "page_number": 1,
                "access": "public",
                "x1": None,
                "x2": None,
                "y1": None,
                "y2": None,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_partial_coords(self, client):
        """You must specify all or none of the coordinates"""
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=document.user)
        response = client.post(
            f"/api/documents/{document.pk}/notes/",
            {
                "title": "Test",
                "content": "Lorem Ipsum",
                "page_number": 1,
                "access": "public",
                "x1": 0.1,
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_bad_coords(self, client):
        """Coordinates must be in order"""
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=document.user)
        response = client.post(
            f"/api/documents/{document.pk}/notes/",
            {
                "title": "Test",
                "content": "Lorem Ipsum",
                "page_number": 1,
                "access": "public",
                "x1": 0.1,
                "x2": 0.2,
                "y1": 0.3,
                "y2": 0.2,
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_private(self, client, user):
        """Create a private note"""
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/documents/{document.pk}/notes/",
            {
                "title": "Test",
                "content": "Lorem Ipsum",
                "page_number": 1,
                "x1": 0.1,
                "x2": 0.2,
                "y1": 0.3,
                "y2": 0.4,
                "access": "private",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = response.json()
        assert Note.objects.filter(pk=response_json["id"]).exists()

    def test_create_bad_page(self, client):
        """Create a note on a non existing page"""
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=document.user)
        response = client.post(
            f"/api/documents/{document.pk}/notes/",
            {"title": "Test", "page_number": 2, "access": "public"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        response = client.post(
            f"/api/documents/{document.pk}/notes/",
            {"title": "Test", "page_number": -1, "access": "public"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_retrieve(self, client, note):
        """Test retrieving a note"""

        response = client.get(f"/api/documents/{note.document.pk}/notes/{note.pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        serializer = NoteSerializer(note)
        assert response_json == serializer.data

    def test_retrieve_expand(self, client, note):
        """Test retrieving a note with an expanded user and organization"""
        response = client.get(
            f"/api/documents/{note.document.pk}/notes/{note.pk}/",
            {"expand": "user,organization"},
        )
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        user_serializer = UserSerializer(note.user)
        organization_serializer = OrganizationSerializer(note.organization)
        assert response_json["user"] == user_serializer.data
        assert response_json["organization"] == organization_serializer.data

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
        """A note's access may be freely changed on a document you can edit"""
        client.force_authenticate(user=note.user)
        response = client.patch(
            f"/api/documents/{note.document.pk}/notes/{note.pk}/",
            {"access": "organization"},
        )
        assert response.status_code == status.HTTP_200_OK
        note.refresh_from_db()
        assert note.access == Access.organization

    def test_update_access_bad_from_private(self, client, user):
        """A note may not be switched from private to public/organization
        if you do not have edit access on the document
        """
        note = NoteFactory(user=user, access=Access.private)
        client.force_authenticate(user=user)
        response = client.patch(
            f"/api/documents/{note.document.pk}/notes/{note.pk}/", {"access": "public"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

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

    def test_create(self, client):
        """Create a section"""
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=document.user)
        response = client.post(
            f"/api/documents/{document.pk}/sections/",
            {"title": "Test", "page_number": 1},
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = response.json()
        assert Section.objects.filter(pk=response_json["id"]).exists()

    def test_create_bad_permission(self, client, user):
        """You may only create sections on documents you can edit"""
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/documents/{document.pk}/sections/",
            {"title": "Test", "page_number": 1},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_bad_page(self, client):
        """You may not create sections on non existent pages"""
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=document.user)

        response = client.post(
            f"/api/documents/{document.pk}/sections/",
            {"title": "Test", "page_number": 9},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        response = client.post(
            f"/api/documents/{document.pk}/sections/",
            {"title": "Test", "page_number": -1},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_bad_duplicate(self, client):
        """You may not create more than one section per page"""
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=document.user)

        response = client.post(
            f"/api/documents/{document.pk}/sections/",
            {"title": "Test", "page_number": 0},
        )
        assert response.status_code == status.HTTP_201_CREATED
        response = client.post(
            f"/api/documents/{document.pk}/sections/",
            {"title": "Test", "page_number": 0},
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

    def test_update_put(self, client, section):
        """Test updating a section
        A section should not conflict with its own page number
        """
        client.force_authenticate(user=section.document.user)
        title = "New Title"
        response = client.put(
            f"/api/documents/{section.document.pk}/sections/{section.pk}/",
            {"title": title, "page_number": section.page_number},
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
class TestLegacyEntityAPI:
    def test_list(self, client, document):
        """List the entities of a document"""
        size = 10
        LegacyEntityFactory.create_batch(size, document=document)
        response = client.get(f"/api/documents/{document.pk}/legacy_entities/")
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
    def _compare_json(self, this, other):
        """Compare without regards to ordering"""
        for key, value in this.items():
            assert sorted(value) == sorted(other[key])

    def test_list(self, client):
        """List the data for a document"""
        document = DocumentFactory(data={"color": ["red", "blue"], "state": ["ma"]})
        response = client.get(f"/api/documents/{document.pk}/data/")
        assert response.status_code == status.HTTP_200_OK
        self._compare_json(response.json(), document.data)

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
        assert sorted(response.json()) == sorted(document.data["color"])

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
        self._compare_json(document.data, {"color": ["red"]})

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
        self._compare_json(
            document.data, {"color": ["green", "yellow"], "state": ["ma"]}
        )

    def test_update_bad_access(self, client, document, user):
        """Add a new key value pair to a document for a document you cannot edit"""
        client.force_authenticate(user=user)
        response = client.put(
            f"/api/documents/{document.pk}/data/color/",
            {"values": ["red"]},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_bad_key(self, client, document):
        """Try adding a non alphanumeric key"""
        client.force_authenticate(user=document.user)
        response = client.put(
            f"/api/documents/{document.pk}/data/bad:key/",
            {"values": ["red"]},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_duplicate(self, client, document):
        """Add a new key value pair to a document with duplicates"""
        client.force_authenticate(user=document.user)
        response = client.put(
            f"/api/documents/{document.pk}/data/color/",
            {"values": ["red", "blue", "red"]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        self._compare_json(document.data, {"color": ["red", "blue"]})

    def test_update_long(self, client, document):
        """Add a new key value pair to a document that is too long"""
        client.force_authenticate(user=document.user)
        response = client.put(
            f"/api/documents/{document.pk}/data/color/",
            {"values": ["a" * 301]},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

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
        assert sorted(document.data["state"]) == sorted(["ma", "nj"])

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
        assert sorted(document.data["state"]) == sorted(["nj", "ca"])

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
        assert sorted(document.data["color"]) == sorted(["blue", "green"])

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

    def test_partial_update_duplicate(self, client):
        """Add an existing value to an existing key"""
        document = DocumentFactory(data={"color": ["red", "blue"], "state": ["ma"]})
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/documents/{document.pk}/data/state/",
            {"values": ["nj", "ma"]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        document.refresh_from_db()
        assert sorted(document.data["state"]) == sorted(["ma", "nj"])

    def test_destroy(self, client):
        """Remove a key"""
        document = DocumentFactory(data={"color": ["red", "blue"], "state": ["ma"]})
        client.force_authenticate(user=document.user)
        response = client.delete(f"/api/documents/{document.pk}/data/state/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        document.refresh_from_db()
        self._compare_json(document.data, {"color": ["red", "blue"]})


@pytest.mark.django_db()
class TestRedactionAPI:
    def test_create(self, client, mocker):
        """Create multiple redactions"""
        mock_redact = mocker.patch("documentcloud.documents.views.redact")
        document = DocumentFactory(page_count=2)
        client.force_authenticate(user=document.user)
        data = [
            {"y1": 0.1, "x1": 0.1, "x2": 0.2, "y2": 0.2, "page_number": 0},
            {"y1": 0.3, "x1": 0.3, "x2": 0.4, "y2": 0.4, "page_number": 1},
        ]
        response = client.post(
            f"/api/documents/{document.pk}/redactions/", data, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        mock_redact.delay.assert_called_once_with(
            document.pk, document.slug, document.access, document.language, data
        )

    def test_create_anonymous(self, client):
        """You cannot create redactions if you are not logged in"""
        document = DocumentFactory(page_count=2)
        data = [
            {"y1": 0.1, "x1": 0.1, "x2": 0.2, "y2": 0.2, "page_number": 0},
            {"y1": 0.3, "x1": 0.3, "x2": 0.4, "y2": 0.4, "page_number": 1},
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
            {"y1": 0.1, "x1": 0.1, "x2": 0.2, "y2": 0.2, "page_number": 0},
            {"y1": 0.3, "x1": 0.3, "x2": 0.4, "y2": 0.4, "page_number": 1},
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
            {"y1": 0.1, "x1": 0.1, "x2": 0.2, "y2": 0.2, "page_number": 0},
            {"y1": 0.3, "x1": 0.3, "x2": 0.4, "y2": 0.4, "page_number": 1},
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
            {"y1": 0.1, "x1": 0.1, "x2": 0.2, "y2": 0.2, "page_number": 0},
            {"y1": 0.3, "x1": 0.3, "x2": 0.4, "y2": 0.4, "page_number": 2},
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
            {"y1": 0.3, "x1": 0.1, "x2": 0.2, "y2": 0.2, "page_number": 0},
            {"y1": 0.3, "x1": 0.5, "x2": 0.4, "y2": 0.4, "page_number": 1},
        ]
        response = client.post(
            f"/api/documents/{document.pk}/redactions/", data, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db()
class TestEntityAPI:
    def test_create(self, client, mocker):
        """Create the entities"""
        document = DocumentFactory(access=Access.private)
        extract_entities = mocker.patch(
            "documentcloud.documents.views.extract_entities.delay"
        )
        client.force_authenticate(user=document.user)
        response = client.post(f"/api/documents/{document.pk}/entities/")
        run_commit_hooks()
        assert response.status_code == status.HTTP_200_OK
        extract_entities.assert_called_once_with(document.pk)

    def test_create_404(self, client, user):
        """Return a 404 if the user cannot view the document"""
        document = DocumentFactory(access=Access.private)
        client.force_authenticate(user=user)
        response = client.post(f"/api/documents/{document.pk}/entities/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_403(self, client, document, user):
        """Return a 403 if the user cannot edit the document"""
        client.force_authenticate(user=user)
        response = client.post(f"/api/documents/{document.pk}/entities/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete(self, client):
        document = DocumentFactory(access=Access.private)
        EntityOccurrenceFactory(document=document)
        client.force_authenticate(user=document.user)
        assert document.entities.count() == 1
        response = client.delete(f"/api/documents/{document.pk}/entities/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert document.entities.count() == 0


@pytest.mark.django_db()
class TestOEmbed:
    def test_oembed(self, client, note):
        """Test oEmbed endpoints"""
        doc_url = "https://www.documentcloud.org" + note.document.get_absolute_url()
        page_url = f"{doc_url}#document/p{note.page_number}"
        note_url = f"{page_url}/a{note.pk}"

        urls = [doc_url, page_url, note_url]
        print(urls)

        for url in urls:
            response = client.get("/api/oembed/", {"url": url})
            assert response.status_code == status.HTTP_200_OK
