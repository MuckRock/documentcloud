# Third Party
import pytest

# DocumentCloud
from documentcloud.organizations.exceptions import InsufficientAICreditsError
from documentcloud.organizations.models import Organization
from documentcloud.organizations.tests.factories import OrganizationFactory
from documentcloud.users.models import User
from documentcloud.users.tests.factories import UserFactory


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
            == 8
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
