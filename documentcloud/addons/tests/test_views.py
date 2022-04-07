# Django
from rest_framework import status

# Third Party
import pytest

# DocumentCloud
from documentcloud.addons.models import AddOn, AddOnRun
from documentcloud.addons.serializers import AddOnRunSerializer, AddOnSerializer
from documentcloud.addons.tests.factories import AddOnFactory, AddOnRunFactory
from documentcloud.documents.choices import Access
from documentcloud.users.tests.factories import UserFactory


@pytest.mark.django_db()
class TestAddOnAPI:
    def test_list(self, client):
        """List add-ons"""
        user = UserFactory()
        viewable = [
            AddOnFactory(access=Access.public),
            AddOnFactory(user=user, access=Access.private),
            AddOnFactory(organization=user.organization, access=Access.organization),
        ]
        non_viewable = [
            AddOnFactory(access=Access.private),
            AddOnFactory(access=Access.organization),
        ]
        client.force_authenticate(user=user)
        response = client.get("/api/addons/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        pks = [r["id"] for r in response_json["results"]]
        assert all(a.pk in pks for a in viewable)
        assert all(a.pk not in pks for a in non_viewable)

    def test_create(self, client):
        """No creating add-ons through the API"""
        user = UserFactory(is_staff=True)
        client.force_authenticate(user=user)
        response = client.post(
            "/api/addons/",
            {
                "name": "Test AddOn",
                "repository": "example/repo",
                "parameters": [{"name": "param1", "type": "text"}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_retrieve(self, client):
        """Test retrieving a new add-on"""
        addon = AddOnFactory()
        client.force_authenticate(user=addon.user)
        response = client.get(f"/api/addons/{addon.pk}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        serializer = AddOnSerializer(addon)
        assert response_json == serializer.data

    def test_update(self, client):
        """Test updating an add-on"""
        addon = AddOnFactory()
        assert addon.access == Access.private
        client.force_authenticate(user=addon.user)
        response = client.patch(f"/api/addons/{addon.pk}/", {"access": "public"})
        assert response.status_code == status.HTTP_200_OK
        addon.refresh_from_db()
        assert addon.access == Access.public

    def test_destroy(self, client):
        """Test destroying an add-on"""
        addon = AddOnFactory()
        client.force_authenticate(user=addon.user)
        response = client.delete(f"/api/addons/{addon.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert AddOn.objects.filter(pk=addon.pk).exists()


@pytest.mark.django_db()
class TestAddOnRunAPI:
    def test_list(self, client):
        """List add-on runs"""
        size = 10
        user = UserFactory(is_staff=True)
        client.force_authenticate(user=user)
        AddOnRunFactory.create_batch(size, user=user)
        response = client.get("/api/addon_runs/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json["results"]) == size

    def test_create(self, client):
        """Test creating a new add-on run"""
        addon = AddOnFactory()
        client.force_authenticate(user=addon.user)
        parameters = {"name": "foobar"}
        response = client.post(
            "/api/addon_runs/",
            {"addon": addon.pk, "parameters": parameters},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        response_json = response.json()
        assert AddOnRun.objects.filter(uuid=response_json["uuid"]).exists()

    def test_create_missing_parameters(self, client):
        """Test creating a new add-on run missing the parameters"""
        addon = AddOnFactory()
        client.force_authenticate(user=addon.user)
        response = client.post("/api/addon_runs/", {"addon": addon.pk}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_parameters_invalid(self, client):
        """Test creating a new add-on run with invalid parameters"""
        addon = AddOnFactory()
        client.force_authenticate(user=addon.user)
        parameters = {"foo": "foobar"}
        response = client.post(
            "/api/addon_runs/",
            {"addon": addon.pk, "parameters": parameters},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_retrieve(self, client):
        """Test retrieving a add-on run"""
        run = AddOnRunFactory()
        client.force_authenticate(user=run.user)
        response = client.get(f"/api/addon_runs/{run.uuid}/")
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        serializer = AddOnRunSerializer(run)
        assert response_json == serializer.data
        assert "presigned_url" not in response_json
        assert response_json["file_url"] is None

    def test_retrieve_upload_file(self, client):
        """Test retrieving a add-on run with the intent to upload a file"""
        run = AddOnRunFactory()
        client.force_authenticate(user=run.user)
        response = client.get(f"/api/addon_runs/{run.uuid}/?upload_file=example.csv")
        assert response.status_code == status.HTTP_200_OK
        assert "presigned_url" in response.json()

    def test_retrieve_download_file(self, client):
        """Test retrieving a add-on run with an available file"""
        run = AddOnRunFactory(file_name="example.csv")
        client.force_authenticate(user=run.user)
        response = client.get(f"/api/addon_runs/{run.uuid}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["file_url"] is not None

    def test_update(self, client):
        """Test updating a add-on run"""
        run = AddOnRunFactory()
        client.force_authenticate(user=run.user)
        progress = 50
        response = client.patch(f"/api/addon_runs/{run.uuid}/", {"progress": progress})
        assert response.status_code == status.HTTP_200_OK
        run.refresh_from_db()
        assert run.progress == progress

    def test_update_bad_progress(self, client):
        """Progress must be between 0 and 100"""
        run = AddOnRunFactory()
        client.force_authenticate(user=run.user)
        progress = 150
        response = client.patch(f"/api/addon_runs/{run.uuid}/", {"progress": progress})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_no_addon(self, client):
        """You may not update the add-on"""
        run = AddOnRunFactory()
        addon = AddOnFactory()
        client.force_authenticate(user=run.user)
        response = client.patch(f"/api/addon_runs/{run.uuid}/", {"addon": addon.pk})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_destroy(self, client):
        """A add-on run may not be destroyed"""
        run = AddOnRunFactory()
        client.force_authenticate(user=run.user)
        response = client.delete(f"/api/addon_runs/{run.uuid}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert AddOnRun.objects.filter(pk=run.pk).exists()
