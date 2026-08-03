# Standard Library
from datetime import date

# Third Party
import pytest

# DocumentCloud
from documentcloud.organizations.exceptions import InsufficientAICreditsError
from documentcloud.organizations.models import Organization
from documentcloud.organizations.tests.factories import (
    EntitlementFactory,
    OrganizationEntitlementFactory,
    OrganizationFactory,
    ProfessionalEntitlementFactory,
)
from documentcloud.users.models import User
from documentcloud.users.tests.factories import UserFactory


def ent_json(entitlement, date_update, quantity=1):
    """Helper function for serializing entitlement data"""
    return {
        "name": entitlement.name,
        "slug": entitlement.slug,
        "description": entitlement.description,
        "resources": entitlement.resources,
        "date_update": date_update,
        "quantity": quantity,
    }


class TestOrganization:

    @pytest.mark.django_db()
    def test_merge(self):

        users = UserFactory.create_batch(4)

        # user 0 and 1 in org
        org = OrganizationFactory(members=users[0:2])
        # user 1 and 2 in dupe org
        dupe_org = OrganizationFactory(members=users[1:3])
        # set active orgs
        users[0].organization = org
        users[1].organization = dupe_org
        users[2].organization = dupe_org

        dupe_org.merge(org.uuid)

        # user 0, 1 and 2 in org
        for user_id in range(3):
            assert org.has_member(users[user_id])
        # user 3 not in org
        assert not org.has_member(users[3])

        # all users have exactly one active org
        for user in User.objects.all():
            assert user.organization

        # no users in dupe_org
        assert dupe_org.users.count() == 0

    @pytest.mark.django_db()
    def test_merge_fks(self):
        # Relations pointing to the Organization model
        assert (
            len(
                [
                    f
                    for f in Organization._meta.get_fields()
                    if f.is_relation and f.auto_created
                ]
            )
            == 9
        )
        # Many to many relations defined on the Organization model
        assert (
            len(
                [
                    f
                    for f in Organization._meta.get_fields()
                    if f.many_to_many and not f.auto_created
                ]
            )
            == 2
        )


class TestSquareletUpdateDataMultiEntitlement:
    """Test cases for update_data with multiple entitlements"""

    def _org_data(self, organization, entitlements):
        return {
            "name": organization.name,
            "slug": organization.slug,
            "individual": False,
            "private": False,
            "entitlements": entitlements,
            "card": "",
        }

    @pytest.mark.django_db()
    def test_two_paid_entitlements_sums_ai_credits(self):
        """Two paid entitlements: ai_credits_per_month = sum of both"""
        ent1 = ProfessionalEntitlementFactory()  # base_ai_credits=2000, min=1
        ent2 = OrganizationEntitlementFactory()  # base_ai_credits=5000, min=5
        organization = OrganizationFactory()
        date_update = date(2024, 3, 1)

        organization.update_data(
            self._org_data(
                organization,
                [
                    ent_json(ent1, date_update, quantity=1),
                    ent_json(ent2, date_update, quantity=5),
                ],
            )
        )
        organization.refresh_from_db()
        # Professional: 2000 + max(0, 1-1)*0 = 2000
        # Organization: 5000 + max(0, 5-5)*500 = 5000
        assert organization.ai_credits_per_month == 7000
        assert organization.monthly_ai_credits == 7000

    @pytest.mark.django_db()
    def test_paid_and_grant_entitlement_sums_ai_credits(self):
        """Paid entitlement + grant entitlement: both contribute to total"""
        paid = OrganizationEntitlementFactory()
        grant = EntitlementFactory(
            name="Grant",
            resources={
                "minimum_users": 1,
                "base_ai_credits": 500,
                "ai_credits_per_user": 0,
                "feature_level": 0,
            },
        )
        organization = OrganizationFactory()
        date_update = date(2024, 3, 1)

        organization.update_data(
            self._org_data(
                organization,
                [
                    ent_json(paid, date_update, quantity=5),
                    ent_json(grant, date_update, quantity=1),
                ],
            )
        )
        organization.refresh_from_db()
        # Organization: 5000 + max(0, 5-5)*500 = 5000, Grant: 500
        assert organization.ai_credits_per_month == 5500
        assert organization.monthly_ai_credits == 5500

    @pytest.mark.django_db()
    def test_primary_entitlement_is_highest_feature_level(self):
        """org.entitlement FK points to entitlement with highest feature_level"""
        low = ProfessionalEntitlementFactory()  # feature_level=1
        high = OrganizationEntitlementFactory()  # feature_level=2
        organization = OrganizationFactory()
        date_update = date(2024, 3, 1)

        organization.update_data(
            self._org_data(
                organization,
                [
                    ent_json(low, date_update, quantity=1),
                    ent_json(high, date_update, quantity=5),
                ],
            )
        )
        organization.refresh_from_db()
        assert organization.entitlement.slug == high.slug

    @pytest.mark.django_db()
    def test_equal_feature_level_tie_breaks_to_first(self):
        """Equal feature_level: first entitlement in list wins the FK"""
        ent1 = EntitlementFactory(
            name="GrantA",
            resources={"base_ai_credits": 100, "feature_level": 1},
        )
        ent2 = EntitlementFactory(
            name="GrantB",
            resources={"base_ai_credits": 200, "feature_level": 1},
        )
        organization = OrganizationFactory()
        date_update = date(2024, 3, 1)

        organization.update_data(
            self._org_data(
                organization,
                [
                    ent_json(ent1, date_update, quantity=1),
                    ent_json(ent2, date_update, quantity=1),
                ],
            )
        )
        organization.refresh_from_db()
        assert organization.entitlement.slug == ent1.slug
        assert organization.ai_credits_per_month == 300

    @pytest.mark.django_db()
    def test_quantity_below_minimum_does_not_reduce_base(self):
        """quantity < minimum_users: base AI credits are not reduced"""
        ent = OrganizationEntitlementFactory()  # min=5, base=5000, per_user=500
        organization = OrganizationFactory()

        organization.update_data(
            self._org_data(organization, [ent_json(ent, date(2024, 3, 1), quantity=2)])
        )
        organization.refresh_from_db()
        # max(0, 2-5) = 0, so just base=5000
        assert organization.ai_credits_per_month == 5000

    @pytest.mark.django_db()
    def test_quantity_above_minimum_adds_per_user_credits(self):
        """quantity > minimum_users: extra quantity adds per-user AI credits"""
        ent = OrganizationEntitlementFactory()  # min=5, base=5000, per_user=500
        organization = OrganizationFactory()

        organization.update_data(
            self._org_data(organization, [ent_json(ent, date(2024, 3, 1), quantity=8)])
        )
        organization.refresh_from_db()
        # 5000 + max(0, 8-5)*500 = 5000 + 1500 = 6500
        assert organization.ai_credits_per_month == 6500

    @pytest.mark.django_db()
    def test_multi_entitlement_monthly_restore(self):
        """Monthly restore resets monthly_ai_credits to sum of all entitlements"""
        ent1 = ProfessionalEntitlementFactory()
        ent2 = OrganizationEntitlementFactory()
        organization = OrganizationFactory(
            entitlement=ent2,
            date_update=date(2024, 2, 1),
            ai_credits_per_month=7000,
            monthly_ai_credits=1000,
        )

        organization.update_data(
            self._org_data(
                organization,
                [
                    ent_json(ent1, date(2024, 3, 1), quantity=1),
                    ent_json(ent2, date(2024, 3, 1), quantity=5),
                ],
            )
        )
        organization.refresh_from_db()
        assert organization.ai_credits_per_month == 7000
        assert organization.monthly_ai_credits == 7000


class TestOrganizationCollective:
    """Tests for Organization collective resource sharing"""

    @pytest.mark.django_db()
    def test_use_ai_credits_with_parent(self):
        """Test using AI credits with parent's resources when own resources exhausted"""
        user = UserFactory()
        parent_org = OrganizationFactory(
            monthly_ai_credits=50, number_ai_credits=25, share_resources=True
        )
        child_org = OrganizationFactory(
            monthly_ai_credits=10, number_ai_credits=5, parent=parent_org
        )

        # Use 15 credits - 10 from child monthly, 5 from child regular
        result = child_org.use_ai_credits(15, user.pk, "Test")

        child_org.refresh_from_db()
        parent_org.refresh_from_db()

        assert result == {"monthly": 10, "regular": 5}
        assert child_org.monthly_ai_credits == 0
        assert child_org.number_ai_credits == 0
        assert parent_org.monthly_ai_credits == 50
        assert parent_org.number_ai_credits == 25

    @pytest.mark.django_db()
    def test_use_ai_credits_parent_no_sharing(self):
        """Test that resources are not shared when parent.share_resources=False"""
        user = UserFactory()
        parent_org = OrganizationFactory(
            monthly_ai_credits=50, number_ai_credits=25, share_resources=False
        )
        child_org = OrganizationFactory(
            monthly_ai_credits=10, number_ai_credits=5, parent=parent_org
        )

        # Try to use 15 credits - should fail after child's 15 credits
        with pytest.raises(InsufficientAICreditsError):
            child_org.use_ai_credits(20, user.pk, "Test")

    @pytest.mark.django_db()
    def test_use_ai_credits_with_groups(self):
        """Test using AI credits with group's resources"""
        user = UserFactory()
        group_org = OrganizationFactory(
            monthly_ai_credits=50, number_ai_credits=25, share_resources=True
        )
        child_org = OrganizationFactory(monthly_ai_credits=10, number_ai_credits=5)
        child_org.groups.add(group_org)

        # Use 20 credits - should use 10 from child monthly, 5 from child regular,
        # 5 from group monthly
        result = child_org.use_ai_credits(20, user.pk, "Test")

        child_org.refresh_from_db()
        group_org.refresh_from_db()

        assert result == {"monthly": 15, "regular": 5}
        assert child_org.monthly_ai_credits == 0
        assert child_org.number_ai_credits == 0
        assert group_org.monthly_ai_credits == 45

    @pytest.mark.django_db()
    def test_use_ai_credits_with_multiple_groups(self):
        """Test using AI credits from multiple groups"""
        user = UserFactory()
        group1 = OrganizationFactory(
            monthly_ai_credits=20, number_ai_credits=10, share_resources=True
        )
        group2 = OrganizationFactory(
            monthly_ai_credits=20, number_ai_credits=10, share_resources=True
        )
        child_org = OrganizationFactory(monthly_ai_credits=10, number_ai_credits=0)
        child_org.groups.add(group1, group2)

        # Use 40 credits - should use 5 from child, then from groups
        result = child_org.use_ai_credits(40, user.pk, "Test")

        child_org.refresh_from_db()
        group1.refresh_from_db()
        group2.refresh_from_db()

        assert result == {"monthly": 30, "regular": 10}
        assert child_org.monthly_ai_credits == 0
        # Groups are consumed in arbitrary order
        assert group1.monthly_ai_credits + group2.monthly_ai_credits == 20
        assert group1.number_ai_credits + group2.number_ai_credits == 10

    @pytest.mark.django_db()
    def test_use_ai_credits_parent_and_groups(self):
        """Test using AI credits with both parent and groups"""
        user = UserFactory()
        parent_org = OrganizationFactory(
            monthly_ai_credits=20, number_ai_credits=10, share_resources=True
        )
        group_org = OrganizationFactory(
            monthly_ai_credits=30, number_ai_credits=15, share_resources=True
        )
        child_org = OrganizationFactory(
            monthly_ai_credits=5, number_ai_credits=0, parent=parent_org
        )
        child_org.groups.add(group_org)

        # Use 60 credits: 5 child monthly, 20 parent monthly, 10 parent regular,
        # 25 group monthly
        result = child_org.use_ai_credits(60, user.pk, "Test")

        child_org.refresh_from_db()
        parent_org.refresh_from_db()
        group_org.refresh_from_db()

        assert result == {"monthly": 50, "regular": 10}
        assert child_org.monthly_ai_credits == 0
        assert child_org.number_ai_credits == 0
        assert parent_org.monthly_ai_credits == 0
        assert parent_org.number_ai_credits == 0
        assert group_org.monthly_ai_credits == 5
        assert group_org.number_ai_credits == 15

    @pytest.mark.django_db()
    def test_get_total_number_ai_credits_own_only(self):
        """Test get_total_number_ai_credits with no parent or groups"""
        org = OrganizationFactory(number_ai_credits=100)
        assert org.get_total_number_ai_credits() == 100

    @pytest.mark.django_db()
    def test_get_total_number_ai_credits_with_parent(self):
        """Test get_total_number_ai_credits including parent"""
        parent_org = OrganizationFactory(number_ai_credits=50, share_resources=True)
        child_org = OrganizationFactory(number_ai_credits=25, parent=parent_org)

        assert child_org.get_total_number_ai_credits() == 75

    @pytest.mark.django_db()
    def test_get_total_number_ai_credits_parent_no_sharing(self):
        """Test get_total_number_ai_credits when parent doesn't share"""
        parent_org = OrganizationFactory(number_ai_credits=50, share_resources=False)
        child_org = OrganizationFactory(number_ai_credits=25, parent=parent_org)

        assert child_org.get_total_number_ai_credits() == 25

    @pytest.mark.django_db()
    def test_get_total_number_ai_credits_with_groups(self):
        """Test get_total_number_ai_credits including groups"""
        group1 = OrganizationFactory(number_ai_credits=30, share_resources=True)
        group2 = OrganizationFactory(number_ai_credits=20, share_resources=True)
        org = OrganizationFactory(number_ai_credits=10)
        org.groups.add(group1, group2)

        assert org.get_total_number_ai_credits() == 60

    @pytest.mark.django_db()
    def test_get_total_monthly_ai_credits_own_only(self):
        """Test get_total_monthly_ai_credits with no parent or groups"""
        org = OrganizationFactory(monthly_ai_credits=50)
        assert org.get_total_monthly_ai_credits() == 50

    @pytest.mark.django_db()
    def test_get_total_monthly_ai_credits_with_parent(self):
        """Test get_total_monthly_ai_credits including parent"""
        parent_org = OrganizationFactory(monthly_ai_credits=100, share_resources=True)
        child_org = OrganizationFactory(monthly_ai_credits=25, parent=parent_org)

        assert child_org.get_total_monthly_ai_credits() == 125

    @pytest.mark.django_db()
    def test_get_total_monthly_ai_credits_with_groups(self):
        """Test get_total_monthly_ai_credits including groups"""
        group1 = OrganizationFactory(monthly_ai_credits=40, share_resources=True)
        group2 = OrganizationFactory(monthly_ai_credits=30, share_resources=True)
        org = OrganizationFactory(monthly_ai_credits=15)
        org.groups.add(group1, group2)

        assert org.get_total_monthly_ai_credits() == 85

    @pytest.mark.django_db()
    def test_insufficient_ai_credits_with_parent(self):
        """Test InsufficientAICreditsError even with parent resources"""
        user = UserFactory()
        parent_org = OrganizationFactory(
            monthly_ai_credits=10, number_ai_credits=5, share_resources=True
        )
        child_org = OrganizationFactory(
            monthly_ai_credits=5, number_ai_credits=2, parent=parent_org
        )

        # Try to use more credits than available (total is 22, trying to use 25)
        with pytest.raises(InsufficientAICreditsError):
            child_org.use_ai_credits(25, user.pk, "Test")
