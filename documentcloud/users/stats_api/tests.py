# Django
from django.utils import timezone
from rest_framework import status

# Standard Library
import json
from datetime import timedelta

# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.tests.factories import DocumentFactory
from documentcloud.users.stats_api.models import UserStats
from documentcloud.users.tests.factories import UserFactory


@pytest.mark.django_db()
class TestUserStatsAPI:
    def _admin(self):
        return UserFactory(is_staff=True)

    def test_list(self, client):
        admin = self._admin()
        client.force_authenticate(user=admin)
        UserFactory.create_batch(3)
        response = client.get("/stats_api/users/")
        assert response.status_code == status.HTTP_200_OK
        body = json.loads(response.content)
        # admin + 3 created + any individual-org users; assert at least the ones we made
        assert len(body["results"]) >= 4

    def test_list_requires_admin(self, client):
        client.force_authenticate(user=UserFactory())  # non-staff
        response = client.get("/stats_api/users/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_unauthenticated(self, client):
        response = client.get("/stats_api/users/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_retrieve_populates_enriched_fields(self, client):
        """Regression: detail view must populate individual_ai_credits and the
        annotated counts, not just the list view (they were only set in
        paginate_queryset before)."""
        admin = self._admin()
        client.force_authenticate(user=admin)

        target = UserFactory()
        # give the individual org credits so individual_ai_credits is non-zero
        org = target.organization
        org.monthly_ai_credits = 5
        org.ai_credits_per_month = 10
        org.save()
        # give them documents so the counts are non-zero
        DocumentFactory.create_batch(2, user=target, organization=org)

        response = client.get(f"/stats_api/users/{target.uuid}/")
        assert response.status_code == status.HTTP_200_OK
        body = json.loads(response.content)

        assert body["total_documents"] == 2
        assert body["recent_upload_count"] == 2
        # the field the review flagged — must be present and reflect the org
        assert body["individual_ai_credits"]["monthly_ai_credits"] == 5
        assert body["individual_ai_credits"]["ai_credits_per_month"] == 10

    def test_filter_uploaded_within_days(self, client):
        admin = self._admin()
        client.force_authenticate(user=admin)
        now = timezone.now()

        recent = UserFactory()
        UserStats.objects.filter(user=recent).update(
            last_upload_at=now - timedelta(days=1)
        )
        old = UserFactory()
        UserStats.objects.filter(user=old).update(
            last_upload_at=now - timedelta(days=30)
        )

        response = client.get("/stats_api/users/", {"uploaded_within_days": 7})
        assert response.status_code == status.HTTP_200_OK
        uuids = {r["uuid"] for r in json.loads(response.content)["results"]}
        assert str(recent.uuid) in uuids
        assert str(old.uuid) not in uuids

    def test_filter_logged_in_within_days(self, client):
        admin = self._admin()
        client.force_authenticate(user=admin)
        now = timezone.now()

        recent = UserFactory(last_login=now - timedelta(days=1))
        old = UserFactory(last_login=now - timedelta(days=30))

        response = client.get("/stats_api/users/", {"logged_in_within_days": 7})
        uuids = {r["uuid"] for r in json.loads(response.content)["results"]}
        assert str(recent.uuid) in uuids
        assert str(old.uuid) not in uuids

    def test_filter_used_ai_credits_within_days(self, client):
        admin = self._admin()
        client.force_authenticate(user=admin)
        now = timezone.now()

        recent = UserFactory()
        UserStats.objects.filter(user=recent).update(
            last_ai_credit_at=now - timedelta(days=1)
        )
        old = UserFactory()
        UserStats.objects.filter(user=old).update(
            last_ai_credit_at=now - timedelta(days=30)
        )

        response = client.get("/stats_api/users/", {"used_ai_credits_within_days": 7})
        uuids = {r["uuid"] for r in json.loads(response.content)["results"]}
        assert str(recent.uuid) in uuids
        assert str(old.uuid) not in uuids

    def test_active_within_days_excludes_ai_credit_only(self, client):
        """active = upload OR login, NOT ai-credit use."""
        admin = self._admin()
        client.force_authenticate(user=admin)
        now = timezone.now()

        uploader = UserFactory()
        UserStats.objects.filter(user=uploader).update(
            last_upload_at=now - timedelta(days=1)
        )
        ai_only = UserFactory(last_login=now - timedelta(days=90))
        UserStats.objects.filter(user=ai_only).update(
            last_ai_credit_at=now - timedelta(days=1)
        )

        response = client.get("/stats_api/users/", {"active_within_days": 7})
        uuids = {r["uuid"] for r in json.loads(response.content)["results"]}
        assert str(uploader.uuid) in uuids
        # AI-credit use alone is NOT activity
        assert str(ai_only.uuid) not in uuids

    def test_record_uploads_sets_watermark(self):
        # DocumentCloud
        from documentcloud.core.utils import record_uploads

        user = UserFactory()
        stats = UserStats.objects.get(user=user)
        assert stats.last_upload_at is None

        record_uploads(user_id=user.pk)

        stats.refresh_from_db()
        assert stats.last_upload_at is not None

    def test_record_ai_credit_use_sets_watermark(self):
        # DocumentCloud
        from documentcloud.core.utils import record_ai_credit_use

        user = UserFactory()
        stats = UserStats.objects.get(user=user)
        assert stats.last_ai_credit_at is None

        record_ai_credit_use(user_id=user.pk)
        stats.refresh_from_db()
        assert stats.last_ai_credit_at is not None
