# Django
from django.db import connection, reset_queries
from django.test.utils import override_settings
from rest_framework import status

# Standard Library
import json

# Third Party
import pytest

# DocumentCloud
from documentcloud.core.tests import run_commit_hooks
from documentcloud.documents.choices import Access
from documentcloud.documents.models import Document
from documentcloud.documents.tests.factories import (
    DocumentFactory,
    NoteFactory,
    SectionFactory,
)
from documentcloud.projects.choices import CollaboratorAccess
from documentcloud.projects.models import Collaboration, Project
from documentcloud.projects.serializers import (
    CollaborationSerializer,
    ProjectMembershipSerializer,
    ProjectSerializer,
)
from documentcloud.projects.tests.factories import ProjectFactory
from documentcloud.users.tests.factories import UserFactory

# pylint: disable=too-many-public-methods


@pytest.mark.django_db()
class TestProjectAPI:
    def test_list(self, client):
        """List projects"""
        size = 10
        ProjectFactory.create_batch(size)
        response = client.get("/api/projects/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert len(response_json["results"]) == size

    def test_create(self, client, user):
        """Create a new project"""
        client.force_authenticate(user=user)
        response = client.post(
            "/api/projects/", {"title": "Test", "description": "This is a test project"}
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = json.loads(response.content)
        project = Project.objects.filter(pk=response_json["id"]).first()
        assert project is not None
        assert project.user == user
        assert project.collaborators.filter(pk=user.pk).exists()

    def test_retrieve(self, client, project):
        """Test retrieving a project"""
        response = client.get(f"/api/projects/{project.pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        serializer = ProjectSerializer(project)
        assert response_json == serializer.data

    def test_update(self, client, project):
        """Test updating a project"""
        client.force_authenticate(user=project.user)
        title = "New Title"
        response = client.patch(f"/api/projects/{project.pk}/", {"title": title})
        assert response.status_code == status.HTTP_200_OK
        project.refresh_from_db()
        assert project.title == title

    def test_update_non_owner_admin(self, client, user):
        """Test updating a project by a non owner admin"""
        project = ProjectFactory(admin_collaborators=[user])
        client.force_authenticate(user=user)
        title = "New Title"
        response = client.patch(f"/api/projects/{project.pk}/", {"title": title})
        assert response.status_code == status.HTTP_200_OK
        project.refresh_from_db()
        assert project.title == title

    def test_update_bad(self, client, user):
        """Test updating a project by a edit collaborator"""
        project = ProjectFactory(edit_collaborators=[user])
        client.force_authenticate(user=user)
        title = "New Title"
        response = client.patch(f"/api/projects/{project.pk}/", {"title": title})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_pin(self, client, project):
        """Test pinning a project"""
        assert not project.user.pinned_projects.filter(pk=project.pk).exists()

        client.force_authenticate(user=project.user)
        response = client.patch(f"/api/projects/{project.pk}/", {"pinned": True})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["pinned"]

        project.refresh_from_db()
        assert project.user.pinned_projects.filter(pk=project.pk).exists()

        response = client.patch(f"/api/projects/{project.pk}/", {"pinned": False})
        assert response.status_code == status.HTTP_200_OK
        assert not response.json()["pinned"]

        project.refresh_from_db()
        assert not project.user.pinned_projects.filter(pk=project.pk).exists()

    def test_destroy(self, client, project):
        """Test destroying a project"""
        client.force_authenticate(user=project.user)
        response = client.delete(f"/api/projects/{project.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Project.objects.filter(pk=project.pk).exists()


@pytest.mark.django_db()
class TestProjectFilters:
    def test_filter_is_shared(self, client):
        """Test filtering projects that are shared with the user"""
        # Create users
        owner = UserFactory()
        collaborator = UserFactory()
        non_collaborator = UserFactory()

        # Create projects
        shared_project = ProjectFactory(user=owner)
        Collaboration.objects.create(
            project=shared_project,
            user=collaborator,
            creator=owner,
            access=CollaboratorAccess.admin,
        )

        # Create a project that the user does not collaborate on
        ProjectFactory(user=non_collaborator)

        # Authenticate as the collaborator
        client.force_authenticate(user=collaborator)

        # Filter for shared projects
        response = client.get("/api/projects/", {"is_shared": True})
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()

        assert len(response_json["results"]) == 1
        assert response_json["results"][0]["id"] == shared_project.id

    def test_filter_owned_by_user(self, client):
        """Test filtering projects owned by the user"""
        # Create users
        owner = UserFactory()
        non_owner = UserFactory()

        # Create projects
        owned_project = ProjectFactory(user=owner)
        non_owned_project = ProjectFactory(user=non_owner)

        # Authenticate as the owner
        client.force_authenticate(user=owner)

        # Filter for owned projects
        response = client.get("/api/projects/", {"owned_by_user": True})
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        # Check if the owned project is in the response
        assert any(p["id"] == owned_project.id for p in response_json["results"])
        # Check that non-owned project is not included
        assert not any(
            p["id"] == non_owned_project.id for p in response_json["results"]
        )


@pytest.mark.django_db()
class TestProjectMembershipAPI:
    def test_list(self, client):
        """List documents in a project"""
        size = 10
        project = ProjectFactory(documents=DocumentFactory.create_batch(size))
        response = client.get(f"/api/projects/{project.pk}/documents/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert len(response_json["results"]) == size

    @pytest.mark.parametrize(
        "expand",
        [
            "",
            "~all",
            (
                "document.user.organization,document.organization,document.projects,"
                "document.sections,document.notes.user.organization,"
                "document.notes.organization"
            ),
        ],
    )
    @override_settings(DEBUG=True)
    def test_list_queries(self, client, expand):
        """Queries should be constant"""
        small_size = 1
        documents = DocumentFactory.create_batch(small_size)
        projects = ProjectFactory.create_batch(small_size, documents=documents)
        for document in documents:
            NoteFactory.create_batch(small_size, document=document)
            SectionFactory.create_batch(small_size, document=document)
        reset_queries()
        client.get(f"/api/projects/{projects[0].pk}/documents/?expand={expand}")
        num_queries = len(connection.queries)

        size = 10
        documents = DocumentFactory.create_batch(size)
        projects = ProjectFactory.create_batch(size, documents=documents)
        for document in documents:
            NoteFactory.create_batch(size, document=document)
            SectionFactory.create_batch(size, document=document)
        reset_queries()
        response = client.get(
            f"/api/projects/{projects[0].pk}/documents/?expand={expand}"
        )
        assert num_queries == len(connection.queries)
        assert len(response.json()["results"]) == size

    def test_list_bad(self, client):
        """List documents in a project including some you cannot view"""
        size = 10
        documents = DocumentFactory.create_batch(size, access=Access.public)
        documents.extend(DocumentFactory.create_batch(size, access=Access.private))
        project = ProjectFactory(documents=documents)
        response = client.get(f"/api/projects/{project.pk}/documents/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert len(response_json["results"]) == size

    def test_create(self, client, project, document):
        """Add a document to a project"""
        client.force_authenticate(user=project.user)
        response = client.post(
            f"/api/projects/{project.pk}/documents/",
            {"document": document.pk},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert project.projectmembership_set.filter(
            document=document, edit_access=False
        ).exists()

    def test_create_implicit_edit(self, client, project):
        """Add a document to a project with edit access"""
        document = DocumentFactory(user=project.user)
        client.force_authenticate(user=project.user)
        response = client.post(
            f"/api/projects/{project.pk}/documents/",
            {"document": document.pk},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert project.projectmembership_set.filter(
            document=document, edit_access=True
        ).exists()

    def test_create_explicit_edit(self, client, project):
        """Add a document to a project with explicit edit access"""
        document = DocumentFactory(user=project.user)
        client.force_authenticate(user=project.user)
        response = client.post(
            f"/api/projects/{project.pk}/documents/",
            {"document": document.pk, "edit_access": True},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert project.projectmembership_set.filter(
            document=document, edit_access=True
        ).exists()

    def test_create_explicit_no_edit(self, client, project):
        """Add a document to a project with explicit no edit access"""
        document = DocumentFactory(user=project.user)
        client.force_authenticate(user=project.user)
        response = client.post(
            f"/api/projects/{project.pk}/documents/",
            {"document": document.pk, "edit_access": False},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert project.projectmembership_set.filter(
            document=document, edit_access=False
        ).exists()

    def test_create_bad_edit_access(self, client, project, document):
        """You may not enable edit access in a project if you do not have edit access"""
        client.force_authenticate(user=project.user)
        response = client.post(
            f"/api/projects/{project.pk}/documents/",
            {"document": document.pk, "edit_access": True},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_bad_no_collaborator(self, client, user, project, document):
        """You may not add a document to a project you are not a collaborator on"""
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/projects/{project.pk}/documents/",
            {"document": document.pk},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_bad_view_collaborator(self, client, user, document):
        """You may not add a document to a project you are a view collaborator on"""
        project = ProjectFactory(collaborators=[user])
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/projects/{project.pk}/documents/",
            {"document": document.pk},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_edit_collaborator(self, client, user, document):
        """You may add a document to a project you are an edit collaborator on"""
        project = ProjectFactory(edit_collaborators=[user])
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/projects/{project.pk}/documents/",
            {"document": document.pk},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_bad_duplicate(self, client, project, document):
        """You may not add the same document to a project more than once"""
        client.force_authenticate(user=project.user)
        response = client.post(
            f"/api/projects/{project.pk}/documents/",
            {"document": document.pk},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert project.documents.filter(pk=document.pk).exists()
        response = client.post(
            f"/api/projects/{project.pk}/documents/", {"document": document.pk}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_bad_no_document(self, client, project):
        """Add a document to a project without ID"""
        client.force_authenticate(user=project.user)
        response = client.post(
            f"/api/projects/{project.pk}/documents/", {"edit_access": False}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_bulk(self, client, project):
        """Add multiple documents to a project"""
        # one the document you own should be added with edit access
        # the other one should not
        documents = [DocumentFactory(user=project.user), DocumentFactory()]
        client.force_authenticate(user=project.user)
        response = client.post(
            f"/api/projects/{project.pk}/documents/",
            [{"document": d.pk} for d in documents],
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert (
            project.documents.filter(projectmembership__edit_access=True).first()
            == documents[0]
        )
        assert (
            project.documents.filter(projectmembership__edit_access=False).first()
            == documents[1]
        )

    def test_retrieve(self, client, document):
        """Test retrieving a document from project"""
        project = ProjectFactory(documents=[document])
        response = client.get(f"/api/projects/{project.pk}/documents/{document.pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        projectmembership = project.projectmembership_set.get(document=document)
        serializer = ProjectMembershipSerializer(projectmembership)
        assert response_json == serializer.data

    def test_retrieve_bad(self, client):
        """Test retrieving a document from project"""
        document = DocumentFactory(access=Access.private)
        project = ProjectFactory(documents=[document])
        response = client.get(f"/api/projects/{project.pk}/documents/{document.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update(self, client, document):
        """Test updating a document in a project"""
        project = ProjectFactory(user=document.user, documents=[document])
        client.force_authenticate(user=project.user)
        response = client.put(
            f"/api/projects/{project.pk}/documents/{document.pk}/",
            {"edit_access": True},
        )
        assert response.status_code == status.HTTP_200_OK
        projectmembership = project.projectmembership_set.get(document=document)
        assert projectmembership.edit_access

    def test_partial_update(self, client, document):
        """Test updating a document in a project"""
        project = ProjectFactory(user=document.user, documents=[document])
        client.force_authenticate(user=project.user)
        response = client.patch(
            f"/api/projects/{project.pk}/documents/{document.pk}/",
            {"edit_access": True},
        )
        assert response.status_code == status.HTTP_200_OK
        projectmembership = project.projectmembership_set.get(document=document)
        assert projectmembership.edit_access

    def test_update_bad_document(self, client):
        """You may not try to change the document ID"""
        documents = DocumentFactory.create_batch(2)
        project = ProjectFactory(user=documents[0].user, documents=[documents[0]])
        client.force_authenticate(user=project.user)
        response = client.patch(
            f"/api/projects/{project.pk}/documents/{documents[0].pk}/",
            {"document": documents[1].pk},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_bad_edit_access(self, client, user, document):
        """You may not enable edit access in a project if you do not have edit access"""
        project = ProjectFactory(user=user, documents=[document])
        client.force_authenticate(user=user)
        response = client.patch(
            f"/api/projects/{project.pk}/documents/{document.pk}/",
            {"edit_access": True},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_bad_no_collaborator(self, client, document):
        """You may not update a document in a project if you are not a collaborator"""
        project = ProjectFactory(documents=[document])
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/projects/{project.pk}/documents/{document.pk}/",
            {"edit_access": True},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_bad_view_collaborator(self, client, document):
        """You may not update a document in a project if you are a view collaborator"""
        project = ProjectFactory(documents=[document], collaborators=[document.user])
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/projects/{project.pk}/documents/{document.pk}/",
            {"edit_access": True},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_edit_collaborator(self, client, document):
        """You may update a document in a project if you are a edit collaborator"""
        project = ProjectFactory(
            documents=[document], edit_collaborators=[document.user]
        )
        client.force_authenticate(user=document.user)
        response = client.patch(
            f"/api/projects/{project.pk}/documents/{document.pk}/",
            {"edit_access": True},
        )
        assert response.status_code == status.HTTP_200_OK

    def test_partial_update_bulk(self, client, user, mocker):
        """Bulk add documents to a project without removing existing documents"""
        mock_solr_index = mocker.patch("documentcloud.documents.tasks.solr_index")
        old_documents = DocumentFactory.create_batch(5, user=user)
        new_documents = old_documents[:2] + DocumentFactory.create_batch(3, user=user)
        # clear solr dirty to test it is set correctly
        Document.objects.filter(
            pk__in=[d.pk for d in old_documents + new_documents]
        ).update(solr_dirty=False)
        for document in old_documents + new_documents:
            document.refresh_from_db()
        project = ProjectFactory(user=user, documents=old_documents)
        other_project = ProjectFactory(user=user, documents=old_documents)
        client.force_authenticate(user=user)
        response = client.patch(
            f"/api/projects/{project.pk}/documents/",
            [{"document": d.pk} for d in new_documents],
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert sorted([d["document"] for d in response_json]) == sorted(
            [d.id for d in new_documents]
        )

        # all of new and old documents are in the project
        assert {d.pk for d in new_documents + old_documents} == {
            d.pk for d in project.documents.all()
        }
        # other project is not changed
        assert {d.pk for d in old_documents} == {
            d.pk for d in other_project.documents.all()
        }
        # check that the solr index was properly updated for all new documents
        for document in old_documents + new_documents:
            document.refresh_from_db()
        assert all(d.solr_dirty for d in new_documents)
        assert all(not d.solr_dirty for d in old_documents[2:])
        run_commit_hooks()
        calls = []
        for doc in new_documents:
            calls.append(
                mocker.call(
                    doc.pk,
                    field_updates={"projects": "set", "projects_edit_access": "set"},
                )
            )
        mock_solr_index.delay.assert_has_calls(calls, any_order=True)

    def test_update_bulk(self, client, user, mocker):
        """Test replacing the document set in a project"""
        mock_solr_index = mocker.patch("documentcloud.documents.tasks.solr_index")
        old_documents = DocumentFactory.create_batch(5, user=user, solr_dirty=False)
        new_documents = old_documents[:2] + DocumentFactory.create_batch(
            3, user=user, solr_dirty=False
        )
        # clear solr dirty to test it is set correctly
        Document.objects.filter(
            pk__in=[d.pk for d in old_documents + new_documents]
        ).update(solr_dirty=False)
        for document in old_documents + new_documents:
            document.refresh_from_db()
        project = ProjectFactory(user=user, documents=old_documents)
        other_project = ProjectFactory(user=user, documents=old_documents)
        client.force_authenticate(user=user)
        response = client.put(
            f"/api/projects/{project.pk}/documents/",
            [{"document": d.pk} for d in new_documents],
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        # new documents exactly matches documents in the project now
        assert {d.pk for d in new_documents} == {d.pk for d in project.documents.all()}
        # other project is not changed
        assert {d.pk for d in old_documents} == {
            d.pk for d in other_project.documents.all()
        }
        # check that the solr index was properly updated for all documents
        for document in old_documents + new_documents:
            document.refresh_from_db()
        assert all(d.solr_dirty for d in old_documents + new_documents[2:])
        run_commit_hooks()
        calls = []
        for doc in old_documents + new_documents[2:]:
            calls.append(
                mocker.call(
                    doc.pk,
                    field_updates={"projects": "set", "projects_edit_access": "set"},
                )
            )
        mock_solr_index.delay.assert_has_calls(calls, any_order=True)

    def test_destroy(self, client, document):
        """Test removing a document from a project"""
        project = ProjectFactory(user=document.user, documents=[document])
        client.force_authenticate(user=project.user)
        response = client.delete(f"/api/projects/{project.pk}/documents/{document.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not project.documents.filter(pk=document.pk).exists()

    def test_destroy_bad_no_collaborator(self, client, user, document):
        """You cannot remove a document from a project you are not a collaborator on"""
        project = ProjectFactory(user=document.user, documents=[document])
        client.force_authenticate(user=user)
        response = client.delete(f"/api/projects/{project.pk}/documents/{document.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_destroy_bad_view_collaborator(self, client, user, document):
        """You cannot remove a document from a project you are a view collaborator on"""
        project = ProjectFactory(
            user=document.user, documents=[document], collaborators=[user]
        )
        client.force_authenticate(user=user)
        response = client.delete(f"/api/projects/{project.pk}/documents/{document.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_destroy_edit_collaborator(self, client, user, document):
        """You can remove a document from a project you are an edit collaborator on"""
        project = ProjectFactory(
            user=document.user, documents=[document], edit_collaborators=[user]
        )
        client.force_authenticate(user=user)
        response = client.delete(f"/api/projects/{project.pk}/documents/{document.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_destroy_bulk(self, client, user):
        """Test removing a document from a project"""
        documents = DocumentFactory.create_batch(3, user=user)
        project = ProjectFactory(user=user, documents=documents)
        client.force_authenticate(user=user)
        doc_ids = ",".join(str(d.pk) for d in documents[:2])
        response = client.delete(
            f"/api/projects/{project.pk}/documents/?document_id__in={doc_ids}"
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert project.documents.count() == 1

    def test_destroy_bulk_bad(self, client, user):
        """Test removing a document from a project you do not have permission to"""
        documents = DocumentFactory.create_batch(3, user=user)
        project = ProjectFactory(documents=documents)
        client.force_authenticate(user=user)
        doc_ids = ",".join(str(d.pk) for d in documents)
        response = client.delete(
            f"/api/projects/{project.pk}/documents/?document_id__in={doc_ids}"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db()
class TestCollaborationAPI:
    def test_list(self, client):
        """List users in a project"""
        size = 10
        project = ProjectFactory(collaborators=UserFactory.create_batch(size))
        client.force_authenticate(user=project.user)
        response = client.get(f"/api/projects/{project.pk}/users/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        # add one for the projects owner
        assert len(response_json["results"]) == size + 1

    @pytest.mark.parametrize("expand", ["", "~all", "user.organization"])
    @override_settings(DEBUG=True)
    def test_list_queries(self, client, expand):
        """Queries should be constant"""
        small_size = 1
        users = UserFactory.create_batch(small_size)
        project = ProjectFactory(collaborators=users)
        client.force_authenticate(user=project.user)
        reset_queries()
        client.get(f"/api/projects/{project.pk}/users/?expand={expand}")
        num_queries = len(connection.queries)

        size = 10
        users = UserFactory.create_batch(size)
        for user_ in users:
            Collaboration.objects.create(user=user_, project=project)
        client.force_authenticate(user=project.user)
        reset_queries()
        response = client.get(f"/api/projects/{project.pk}/users/?expand={expand}")
        assert num_queries == len(connection.queries)
        assert len(response.json()["results"]) == size + small_size + 1

    def test_create(self, client, project, user):
        """Add a user to a project"""
        client.force_authenticate(user=project.user)
        response = client.post(
            f"/api/projects/{project.pk}/users/", {"email": user.email}
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert project.collaborators.filter(pk=user.pk).exists()

    def test_create_bad_collaborator(self, client, project, user):
        """You may not add a collaborator to a project you are not a collaborator on"""
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/projects/{project.pk}/users/", {"email": user.email}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_bad_edit_collaborator(self, client, user):
        """You may not add a collaborator to a project you are just an edit
        collaborator on
        """
        project = ProjectFactory(edit_collaborators=[user])
        other_user = UserFactory()
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/projects/{project.pk}/users/", {"email": other_user.email}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_bad_email(self, client, project):
        """Trying adding an email without a user"""
        client.force_authenticate(user=project.user)
        response = client.post(
            f"/api/projects/{project.pk}/users/", {"email": "bad@example.com"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_bad_duplicate(self, client, project, user):
        """May not add a user more than once"""
        client.force_authenticate(user=project.user)
        response = client.post(
            f"/api/projects/{project.pk}/users/", {"email": user.email}
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert project.collaborators.filter(pk=user.pk).exists()
        response = client.post(
            f"/api/projects/{project.pk}/users/", {"email": user.email}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_retrieve(self, client, user):
        """Test retrieving a user from project"""
        project = ProjectFactory(collaborators=[user])
        client.force_authenticate(user=project.user)
        response = client.get(f"/api/projects/{project.pk}/users/{user.pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        collaboration = project.collaboration_set.get(user=user)
        serializer = CollaborationSerializer(collaboration)
        assert response_json == serializer.data

    def test_update(self, client, user):
        """Test updating a collaborator in a project"""
        project = ProjectFactory(collaborators=[user])
        client.force_authenticate(user=project.user)
        response = client.patch(
            f"/api/projects/{project.pk}/users/{user.pk}/", {"access": "admin"}
        )
        assert response.status_code == status.HTTP_200_OK
        collaborator = project.collaboration_set.get(user=user)
        assert collaborator.access == CollaboratorAccess.admin

    def test_update_bad_user(self, client, user):
        """You may not change a user on a Collaboration"""
        project = ProjectFactory(collaborators=[user])
        client.force_authenticate(user=project.user)
        response = client.patch(
            f"/api/projects/{project.pk}/users/{user.pk}/", {"email": "foo@example.com"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_bad_admin(self, client):
        """You may not remove admin permissions from the last admin"""
        project = ProjectFactory()
        client.force_authenticate(user=project.user)
        response = client.patch(
            f"/api/projects/{project.pk}/users/{project.user.pk}/", {"access": "edit"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_destroy(self, client, user):
        """Test removing a user from a project"""
        project = ProjectFactory(admin_collaborators=[user])
        client.force_authenticate(user=project.user)
        response = client.delete(f"/api/projects/{project.pk}/users/{user.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not project.collaborators.filter(pk=user.pk).exists()

    def test_destroy_bad_admin(self, client):
        """You may not remove the last admin from a project"""
        project = ProjectFactory()
        client.force_authenticate(user=project.user)
        response = client.delete(f"/api/projects/{project.pk}/users/{project.user.pk}/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_destroy_bad_collaborator(self, client, user, project):
        """You cannot remove a user from a project you are not a collaborator on"""
        client.force_authenticate(user=user)
        response = client.delete(f"/api/projects/{project.pk}/users/{project.user.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
