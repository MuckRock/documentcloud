# Django
from django.conf import settings
from rest_framework import status

# Standard Library
import json

# Third Party
import pytest

# DocumentCloud
from documentcloud.projects.tests.factories import ProjectFactory
from documentcloud.sidekick.choices import Status
from documentcloud.sidekick.models import Sidekick
from documentcloud.users.tests.factories import UserFactory


@pytest.mark.django_db()
class TestSidekickAPI:
    def test_create(self, client, project):
        """Create a new sidekick"""
        client.force_authenticate(user=project.user)
        response = client.post(f"/api/projects/{project.pk}/sidekick/")
        assert response.status_code == status.HTTP_201_CREATED
        response_json = json.loads(response.content)
        assert response_json == {"status": "pending"}

    def test_create_no_perm(self, client, project, user):
        """Create a new sidekick for a project you are not an editor for"""
        client.force_authenticate(user=user)
        response = client.post(f"/api/projects/{project.pk}/sidekick/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_reprocess(self, client, project):
        """Use `create` to reprocess an existing sidekick"""
        Sidekick.objects.create(project=project, status=Status.success)
        client.force_authenticate(user=project.user)
        response = client.post(f"/api/projects/{project.pk}/sidekick/")
        assert response.status_code == status.HTTP_201_CREATED
        response_json = json.loads(response.content)
        assert response_json == {}

    def test_create_reprocess_pending(self, client, project):
        """It is an error to attempt to re-process while already processing"""
        Sidekick.objects.create(project=project, status=Status.pending)
        client.force_authenticate(user=project.user)
        response = client.post(f"/api/projects/{project.pk}/sidekick/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        response_json = json.loads(response.content)
        assert response_json == ["Already processing"]

    def test_retrieve(self, client, project):
        """Retrieve a sidekick"""
        client.force_authenticate(user=project.user)
        Sidekick.objects.create(project=project)
        response = client.get(f"/api/projects/{project.pk}/sidekick/")
        assert response.status_code == status.HTTP_200_OK

    def test_retrieve_no_exist(self, client, project):
        """Retrieve a sidekick but no sidekick"""
        client.force_authenticate(user=project.user)
        response = client.get(f"/api/projects/{project.pk}/sidekick/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_no_perm(self, client, project, user):
        """Retrieve a sidekick but no permissions"""
        client.force_authenticate(user=user)
        response = client.get(f"/api/projects/{project.pk}/sidekick/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete(self, client, project):
        """Delete a sidekick"""
        Sidekick.objects.create(project=project, status=Status.success)
        client.force_authenticate(user=project.user)
        response = client.delete(f"/api/projects/{project.pk}/sidekick/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_no_perm(self, client, project, user):
        """Delete a sidekick without permissions"""
        Sidekick.objects.create(project=project, status=Status.success)
        client.force_authenticate(user=user)
        response = client.delete(f"/api/projects/{project.pk}/sidekick/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_no_exist(self, client, project):
        """Delete a sidekick with no sidekick"""
        client.force_authenticate(user=project.user)
        response = client.delete(f"/api/projects/{project.pk}/sidekick/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update(self, client, project):
        """Update a sidekick - nothing to update for normal users"""
        Sidekick.objects.create(project=project, status=Status.success)
        client.force_authenticate(user=project.user)
        response = client.patch(f"/api/projects/{project.pk}/sidekick/", {})
        assert response.status_code == status.HTTP_200_OK

    def test_update_processing_token(self, client, project):
        """Update a sidekick with a processing token"""
        Sidekick.objects.create(project=project, status=Status.pending)
        response = client.patch(
            f"/api/projects/{project.pk}/sidekick/",
            {"status": "success"},
            HTTP_AUTHORIZATION=f"processing-token {settings.PROCESSING_TOKEN}",
        )
        assert response.status_code == status.HTTP_200_OK
        response_json = json.loads(response.content)
        assert response_json == {"status": "success"}

    def test_update_no_exist(self, client, project):
        """Update a sidekick that doesn't exist"""
        client.force_authenticate(user=project.user)
        response = client.patch(f"/api/projects/{project.pk}/sidekick/", {})
        assert response.status_code == status.HTTP_404_NOT_FOUND
