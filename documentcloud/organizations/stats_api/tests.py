# Django
from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from rest_framework import status

# Standard Library
import json
from datetime import timedelta

# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.models import Document
from documentcloud.documents.tests.factories import DocumentFactory
from documentcloud.organizations.models import (  # confirm extra required fields
    Organization,
)
from documentcloud.organizations.stats_api.models import OrganizationStats
from documentcloud.organizations.tests.factories import OrganizationFactory
from documentcloud.users.tests.factories import UserFactory


class OrgTotalCreditsQueryTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.parent = OrganizationFactory(
            share_resources=True,
            number_ai_credits=100,
            monthly_ai_credits=100,
            ai_credits_per_month=100,
        )
        cls.org = OrganizationFactory(
            parent=cls.parent,
            share_resources=True,
            number_ai_credits=10,
            monthly_ai_credits=10,
            ai_credits_per_month=10,
        )
        cls.sharing_group = OrganizationFactory(
            share_resources=True,
            number_ai_credits=5,
            monthly_ai_credits=5,
            ai_credits_per_month=5,
        )
        cls.non_sharing_group = OrganizationFactory(
            share_resources=False,
            number_ai_credits=999,
            monthly_ai_credits=999,
            ai_credits_per_month=999,
        )
        cls.org.groups.set([cls.sharing_group, cls.non_sharing_group])
        cls.user = UserFactory()

    def test_total_credits_use_prefetch_cache(self):
        # Mirror the stats endpoint's fetch.
        org = (
            Organization.objects.select_related("parent")
            .prefetch_related("groups")
            .get(pk=self.org.pk)
        )
        # Regression test against N+1 behavior in get_total methods.
        # parent (select_related) + groups (prefetch) already loaded.
        with self.assertNumQueries(0):
            org.get_total_number_ai_credits()
            org.get_total_monthly_ai_credits()
            org.get_total_monthly_ai_credits_allowance()

    def test_totals_are_correct(self):
        org = (
            Organization.objects.select_related("parent")
            .prefetch_related("groups")
            .get(pk=self.org.pk)
        )
        # self + sharing parent + sharing group
        # non_sharing_group's 999 excluded.
        self.assertEqual(org.get_total_number_ai_credits(), 10 + 100 + 5)
        self.assertEqual(org.get_total_monthly_ai_credits(), 10 + 100 + 5)
        self.assertEqual(org.get_total_monthly_ai_credits_allowance(), 10 + 100 + 5)

    def test_totals_match_use_ai_credits_consumption(self):
        org = Organization.objects.get(pk=self.org.pk)
        total_monthly = org.get_total_monthly_ai_credits()
        total_number = org.get_total_number_ai_credits()
        consumed = org.use_ai_credits(
            amount=total_monthly + total_number,
            user_id=self.user.pk,
            note="test drain",
        )
        self.assertEqual(consumed["monthly"], total_monthly)
        self.assertEqual(consumed["regular"], total_number)


@pytest.mark.django_db()
class TestOrganizationStatsAPI:
    def _admin(self):
        return UserFactory(is_staff=True)

    def test_list_requires_admin(self, client):
        client.force_authenticate(user=UserFactory())
        response = client.get("/stats_api/organizations/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_unauthenticated(self, client):
        response = client.get("/stats_api/organizations/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_excludes_individual_orgs(self, client):
        """Users pull individual orgs in on the users endpoint"""
        client.force_authenticate(user=self._admin())
        collective = OrganizationFactory.create_batch(3, individual=False)
        individual = OrganizationFactory(individual=True)
        response = client.get("/stats_api/organizations/")
        assert response.status_code == status.HTTP_200_OK
        uuids = {r["uuid"] for r in json.loads(response.content)["results"]}
        for org in collective:
            assert str(org.uuid) in uuids
        # get_queryset filters individual=False
        assert str(individual.uuid) not in uuids

    def test_retrieve_populates_enriched_fields(self, client):
        """Regression test. org detail view populates the annotated counts, which
        were previously only set in paginate_queryset (list view)."""
        client.force_authenticate(user=self._admin())
        org = OrganizationFactory(individual=False)
        DocumentFactory.create_batch(2, organization=org)

        response = client.get(f"/stats_api/organizations/{org.uuid}/")
        assert response.status_code == status.HTTP_200_OK
        body = json.loads(response.content)
        assert body["total_documents"] == 2
        assert body["recent_upload_count"] == 2

    def test_filter_uploaded_within_days(self, client):
        client.force_authenticate(user=self._admin())
        now = timezone.now()

        recent = OrganizationFactory(individual=False)
        OrganizationStats.objects.filter(organization=recent).update(
            last_upload_at=now - timedelta(days=1)
        )
        old = OrganizationFactory(individual=False)
        OrganizationStats.objects.filter(organization=old).update(
            last_upload_at=now - timedelta(days=30)
        )

        response = client.get("/stats_api/organizations/", {"uploaded_within_days": 7})
        assert response.status_code == status.HTTP_200_OK
        uuids = {r["uuid"] for r in json.loads(response.content)["results"]}
        assert str(recent.uuid) in uuids
        assert str(old.uuid) not in uuids

    def test_document_upload_bumps_org_watermark(
        self, client, user_with_collective_org
    ):
        user, org = user_with_collective_org
        client.force_authenticate(user=user)

        print("fixture org:", org.pk)
        print("user.organization:", user.organization.pk)  # same as org.pk?

        response = client.post("/api/documents/", {"title": "t"})
        print("status:", response.status_code, response.content[:200])  # created?

        stats = OrganizationStats.objects.get(organization=org)
        assert stats.last_upload_at is not None

    def test_ai_credit_charge_bumps_org_watermark(
        self, client, user_with_collective_org
    ):
        """use_ai_credits' record_ai_credit_use call should bump the org watermark."""

        user, org = user_with_collective_org
        # give the org credits to spend
        org.monthly_ai_credits = 5
        org.save()
        assert OrganizationStats.objects.get(organization=org).last_ai_credit_at is None

        response = client.post(
            f"/api/organizations/{org.pk}/ai_credits/",
            {"ai_credits": 1, "user_id": user.pk},
            HTTP_AUTHORIZATION=f"processing-token {settings.PROCESSING_TOKEN}",
        )
        assert response.status_code == status.HTTP_200_OK

        stats = OrganizationStats.objects.get(organization=org)
        assert stats.last_ai_credit_at is not None

    def test_aged_out_requires_since(self, client):
        client.force_authenticate(user=self._admin())
        response = client.get("/stats_api/organizations/aged_out/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_aged_out_invalid_since(self, client):
        client.force_authenticate(user=self._admin())
        response = client.get(
            "/stats_api/organizations/aged_out/", {"since": "not-a-date"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_aged_out_returns_boundary_crossers(self, client):
        """Test that aged_out catches boundary crossers"""
        client.force_authenticate(user=self._admin())
        now = timezone.now()
        win = timedelta(days=settings.UPLOAD_WINDOW_DAYS)

        # org with a doc that aged out of the window since `since`
        aged = OrganizationFactory(individual=False)
        doc = DocumentFactory(organization=aged)
        # created_at is auto_now_add
        Document.objects.filter(pk=doc.pk).update(
            created_at=now - win - timedelta(days=1)
        )

        # org with only a fresh doc — still in window, should NOT appear
        fresh = OrganizationFactory(individual=False)
        DocumentFactory(organization=fresh)  # created_at = now

        since = (now - timedelta(days=2)).isoformat()
        response = client.get("/stats_api/organizations/aged_out/", {"since": since})
        assert response.status_code == status.HTTP_200_OK
        uuids = {r["uuid"] for r in json.loads(response.content)["results"]}
        assert str(aged.uuid) in uuids
        assert str(fresh.uuid) not in uuids
