# Third Party
# Django
from rest_framework import status

# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.tests.factories import SavedSearchFactory


@pytest.mark.django_db()
class TestSavedSearchAPI:
    base_url = "/api/documents/search/saved/"

    def test_list_unauthenticated(self, client):
        """Anonymous GET returns 403"""
        response = client.get(self.base_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_unauthenticated(self, client):
        """Anonymous POST returns 403"""
        response = client.post(self.base_url, {"name": "Test", "query": "test"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_unauthenticated(self, client):
        """Anonymous DELETE returns 403"""
        saved_search = SavedSearchFactory()
        response = client.delete(f"{self.base_url}{saved_search.uuid}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_retrieve_unauthenticated(self, client):
        """Anonymous GET for a single search returns 403"""
        saved_search = SavedSearchFactory()
        response = client.get(f"{self.base_url}{saved_search.uuid}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list(self, client, user):
        """Authenticated user sees only their own saved searches"""
        client.force_authenticate(user=user)
        SavedSearchFactory.create_batch(2)  # other user's searches
        owned = SavedSearchFactory.create_batch(3, user=user)
        response = client.get(self.base_url)
        assert response.status_code == status.HTTP_200_OK
        results = response.json()["results"]
        result_uuids = {r["uuid"] for r in results}
        expected_uuids = {str(s.uuid) for s in owned}
        assert result_uuids == expected_uuids

    def test_create(self, client, user):
        """POST with name + query creates a saved search for the user"""
        client.force_authenticate(user=user)
        data = {"name": "My Search", "query": "title:test"}
        response = client.post(self.base_url, data)
        assert response.status_code == status.HTTP_201_CREATED
        result = response.json()
        assert result["name"] == "My Search"
        assert result["query"] == "title:test"
        assert "uuid" in result
        assert "created_at" in result
        assert "updated_at" in result

    def test_retrieve(self, client, user):
        """GET a single saved search by UUID"""
        client.force_authenticate(user=user)
        saved_search = SavedSearchFactory(user=user)
        response = client.get(f"{self.base_url}{saved_search.uuid}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["name"] == saved_search.name

    def test_retrieve_other_user(self, client, user):
        """Can't see another user's saved search (404)"""
        client.force_authenticate(user=user)
        saved_search = SavedSearchFactory()  # different user
        response = client.get(f"{self.base_url}{saved_search.uuid}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_name(self, client, user):
        """PATCH to update name"""
        client.force_authenticate(user=user)
        saved_search = SavedSearchFactory(user=user)
        response = client.patch(
            f"{self.base_url}{saved_search.uuid}/",
            {"name": "Updated Name"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["name"] == "Updated Name"

    def test_update_query(self, client, user):
        """PATCH to update query"""
        client.force_authenticate(user=user)
        saved_search = SavedSearchFactory(user=user)
        response = client.patch(
            f"{self.base_url}{saved_search.uuid}/",
            {"query": "new query"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["query"] == "new query"

    def test_update_other_user(self, client, user):
        """Can't update another user's saved search (404)"""
        client.force_authenticate(user=user)
        saved_search = SavedSearchFactory()  # different user
        response = client.patch(
            f"{self.base_url}{saved_search.uuid}/",
            {"name": "Hacked"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete(self, client, user):
        """DELETE removes the saved search"""
        client.force_authenticate(user=user)
        saved_search = SavedSearchFactory(user=user)
        response = client.delete(f"{self.base_url}{saved_search.uuid}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        # Verify it's gone
        response = client.get(f"{self.base_url}{saved_search.uuid}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_other_user(self, client, user):
        """Can't delete another user's saved search (404)"""
        client.force_authenticate(user=user)
        saved_search = SavedSearchFactory()  # different user
        response = client.delete(f"{self.base_url}{saved_search.uuid}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
