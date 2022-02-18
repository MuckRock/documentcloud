# Django
from rest_framework import status

# Standard Library
from uuid import UUID

# Third Party
import pytest

# DocumentCloud
from documentcloud.plugins.models import Plugin, PluginRun
from documentcloud.plugins.serializers import PluginRunSerializer, PluginSerializer
from documentcloud.plugins.tests.factories import PluginFactory, PluginRunFactory
from documentcloud.users.tests.factories import UserFactory


@pytest.mark.django_db()
class TestPluginAPI:
    def test_list(self, client):
        """Non-staff cannot view plugins"""
        size = 10
        PluginFactory.create_batch(size)
        response = client.get("/api/plugins/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["results"]) == 0

    def test_list_staff(self, client):
        """Staff can list plugins"""
        size = 10
        user = UserFactory(is_staff=True)
        client.force_authenticate(user=user)
        PluginFactory.create_batch(size)
        response = client.get("/api/plugins/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["results"]) == size

    def test_create(self, client):
        """Test creating a new plugin"""
        user = UserFactory(is_staff=True)
        client.force_authenticate(user=user)
        response = client.post(
            "/api/plugins/",
            {
                "name": "Test Plugin",
                "repository": "example/repo",
                "parameters": [{"name": "param1", "type": "text"}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = response.json()
        assert Plugin.objects.filter(pk=response_json["id"]).exists()

    def test_retrieve(self, client):
        """Test retrieving a new plugin"""
        plugin = PluginFactory()
        client.force_authenticate(user=plugin.user)
        response = client.get(f"/api/plugins/{plugin.pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        serializer = PluginSerializer(plugin)
        assert response_json == serializer.data

    def test_update(self, client):
        """Test updating a plugin"""
        plugin = PluginFactory()
        client.force_authenticate(user=plugin.user)
        name = "New name"
        response = client.patch(f"/api/plugins/{plugin.pk}/", {"name": name})
        assert response.status_code == status.HTTP_200_OK
        plugin.refresh_from_db()
        assert plugin.name == name

    def test_destroy(self, client):
        """Test destroying a plugin"""
        plugin = PluginFactory()
        client.force_authenticate(user=plugin.user)
        response = client.delete(f"/api/plugins/{plugin.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Plugin.objects.filter(pk=plugin.pk).exists()


@pytest.mark.django_db()
class TestPluginRunAPI:
    def test_list(self, client):
        """List plugin runs"""
        size = 10
        user = UserFactory(is_staff=True)
        client.force_authenticate(user=user)
        PluginRunFactory.create_batch(size, user=user)
        response = client.get("/api/plugin_runs/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["results"]) == size

    def test_create(self, client, mocker):
        """Test creating a new plugin run"""
        mock_dispatch = mocker.patch("documentcloud.plugins.models.Plugin.dispatch")
        user = UserFactory(is_staff=True)
        plugin = PluginFactory()
        client.force_authenticate(user=user)
        parameters = {"test": "foobar"}
        response = client.post(
            "/api/plugin_runs/",
            {"plugin": plugin.pk, "parameters": parameters},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = response.json()
        assert PluginRun.objects.filter(uuid=response_json["uuid"]).exists()
        mock_dispatch.assert_called_once_with(
            UUID(response_json["uuid"]), user, None, None, parameters
        )

    def test_create_missing_parameters(self, client):
        """Test creating a new plugin run"""
        user = UserFactory(is_staff=True)
        plugin = PluginFactory()
        client.force_authenticate(user=user)
        response = client.post(
            "/api/plugin_runs/", {"plugin": plugin.pk}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_missing_parameter_key(self, client):
        """Test creating a new plugin run"""
        user = UserFactory(is_staff=True)
        plugin = PluginFactory()
        client.force_authenticate(user=user)
        parameters = {"foo": "foobar"}
        response = client.post(
            "/api/plugin_runs/",
            {"plugin": plugin.pk, "parameters": parameters},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_retrieve(self, client):
        """Test retrieving a plugin run"""
        run = PluginRunFactory()
        client.force_authenticate(user=run.user)
        response = client.get(f"/api/plugin_runs/{run.uuid}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        serializer = PluginRunSerializer(run)
        assert response_json == serializer.data
        assert "presigned_url" not in response_json
        assert response_json["file_url"] is None

    def test_retrieve_upload_file(self, client):
        """Test retrieving a plugin run with the intent to upload a file"""
        run = PluginRunFactory()
        client.force_authenticate(user=run.user)
        response = client.get(f"/api/plugin_runs/{run.uuid}/?upload_file=example.csv")
        assert response.status_code == status.HTTP_200_OK
        assert "presigned_url" in response.json()

    def test_retrieve_download_file(self, client):
        """Test retrieving a plugin run with an available file"""
        run = PluginRunFactory(file_name="example.csv")
        client.force_authenticate(user=run.user)
        response = client.get(f"/api/plugin_runs/{run.uuid}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["file_url"] is not None

    def test_update(self, client):
        """Test updating a plugin run"""
        run = PluginRunFactory()
        client.force_authenticate(user=run.user)
        progress = 50
        response = client.patch(f"/api/plugin_runs/{run.uuid}/", {"progress": progress})
        assert response.status_code == status.HTTP_200_OK
        run.refresh_from_db()
        assert run.progress == progress

    def test_update_bad_progress(self, client):
        """Progress must be between 0 and 100"""
        run = PluginRunFactory()
        client.force_authenticate(user=run.user)
        progress = 150
        response = client.patch(f"/api/plugin_runs/{run.uuid}/", {"progress": progress})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_no_plugin(self, client):
        """You may not update the plugin"""
        run = PluginRunFactory()
        plugin = PluginFactory()
        client.force_authenticate(user=run.user)
        response = client.patch(f"/api/plugin_runs/{run.uuid}/", {"plugin": plugin.pk})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_destroy(self, client):
        """A plugin run may not be destroyed"""
        run = PluginRunFactory()
        client.force_authenticate(user=run.user)
        response = client.delete(f"/api/plugin_runs/{run.uuid}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert PluginRun.objects.filter(pk=run.pk).exists()
