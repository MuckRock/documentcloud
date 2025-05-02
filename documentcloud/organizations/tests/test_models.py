# Third Party
import pytest

# DocumentCloud
from documentcloud.organizations.models import Organization
from documentcloud.organizations.tests.factories import OrganizationFactory
from documentcloud.users.tests.factories import UserFactory


class TestOrganization:

    @pytest.mark.django_db()
    def test_merge(self):

        users = UserFactory.create_batch(4)

        # user 0 and 1 in org
        org = OrganizationFactory(members=users[0:2])
        # user 1 and 2 in dupe org
        dupe_org = OrganizationFactory(members=users[1:3])

        dupe_org.merge(org.uuid)

        # user 0, 1 and 2 in org
        for user_id in range(3):
            assert org.has_member(users[user_id])
        # user 3 not in org
        assert not org.has_member(users[3])

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
            == 6
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
            == 1
        )
