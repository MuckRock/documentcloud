# Django
from django.test import TestCase

# DocumentCloud
from documentcloud.organizations.models import (  # confirm extra required fields
    Organization,
)
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

    def test_total_credits_use_prefetch_cache_no_n_plus_one(self):
        # Mirror the stats endpoint's fetch.
        org = (
            Organization.objects.select_related("parent")
            .prefetch_related("groups")
            .get(pk=self.org.pk)
        )
        # parent (select_related) + groups (prefetch) already loaded; the methods
        # filter groups in Python via self.groups.all(). All three calls => 0 queries.
        # Revert any method to self.groups.filter(share_resources=True) and this
        # becomes 3, failing with the offending SQL.
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
        # self + sharing parent + sharing group; non_sharing_group's 999 excluded.
        self.assertEqual(org.get_total_number_ai_credits(), 10 + 100 + 5)
        self.assertEqual(org.get_total_monthly_ai_credits(), 10 + 100 + 5)
        self.assertEqual(org.get_total_monthly_ai_credits_allowance(), 10 + 100 + 5)

    def test_python_filter_matches_orm_filter(self):
        """'all()+Python == .filter(share_resources=True)."""
        org = Organization.objects.prefetch_related("groups").get(pk=self.org.pk)
        python_side = {g.pk for g in org.groups.all() if g.share_resources}
        orm_side = set(
            org.groups.filter(share_resources=True).values_list("pk", flat=True)
        )
        self.assertEqual(python_side, orm_side)

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
