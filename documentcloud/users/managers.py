"""Custom querysets for account app"""

# Django
from django.contrib.auth.models import UserManager as AuthUserManager
from django.db import transaction

# Standard Library
import logging

# DocumentCloud
from documentcloud.organizations.models import Membership, Organization
from documentcloud.users.querysets import UserQuerySet

logger = logging.getLogger(__name__)


class BaseUserManager(AuthUserManager):
    """Object manager for users"""

    @transaction.atomic
    def squarelet_update_or_create(self, uuid, data):
        """Update or create records based on data from squarelet"""

        required_fields = {"preferred_username", "organizations"}
        missing = required_fields - (required_fields & set(data.keys()))
        if missing:
            raise ValueError("Missing required fields: {}".format(missing))

        if data.get("is_agency"):
            # do not create agency users on documentcloud
            return None, False

        user, created = self._squarelet_update_or_create_user(uuid, data)

        self._update_organizations(user, data)

        return user, created

    def _squarelet_update_or_create_user(self, uuid, data):
        """Format user data and update or create the user"""
        user_map = {
            "preferred_username": "username",
            "email": "email",
            "name": "name",
            "picture": "avatar_url",
            "email_failed": "email_failed",
            "email_verified": "email_verified",
            "use_autologin": "use_autologin",
        }
        user_defaults = {
            "preferred_username": "",
            "email": "",
            "name": "",
            "picture": "",
            "email_failed": False,
            "email_verified": False,
            "use_autologin": True,
        }
        user_data = {user_map[k]: data.get(k, user_defaults[k]) for k in user_map}
        return self.update_or_create(uuid=uuid, defaults=user_data)

    def _update_organizations(self, user, data):
        """Update the user's organizations"""
        current_organizations = set(user.organizations.all())
        new_memberships = []
        active = True

        # process each organization
        for org_data in data.get("organizations", []):
            organization, _ = Organization.objects.squarelet_update_or_create(
                uuid=org_data["uuid"], data=org_data
            )
            if organization in current_organizations:
                # remove organizations from our set as we see them
                # any that are left will need to be removed
                current_organizations.remove(organization)
                user.memberships.filter(organization=organization).update(
                    admin=org_data["admin"]
                )
            else:
                # if not currently a member, create the new membership
                # automatically activate new organizations (only first one)
                new_memberships.append(
                    Membership(
                        user=user,
                        organization=organization,
                        active=active,
                        admin=org_data["admin"],
                    )
                )
                active = False

        if new_memberships:
            # first new membership will be made active, de-activate current
            # active org first
            user.memberships.filter(active=True).update(active=False)
            user.memberships.bulk_create(new_memberships)

        # user must have an active organization, if the current
        # active one is removed, we will activate the user's individual organization
        if user.organization in current_organizations:
            user.memberships.filter(organization__individual=True).update(active=True)

        # never remove the user's individual organization
        individual_organization = user.memberships.get(organization__individual=True)
        if individual_organization in current_organizations:
            logger.error("Trying to remove a user's individual organization: %s", user)
            current_organizations.remove(individual_organization)

        user.memberships.filter(organization__in=current_organizations).delete()


class UserManager(BaseUserManager.from_queryset(UserQuerySet)):
    pass
