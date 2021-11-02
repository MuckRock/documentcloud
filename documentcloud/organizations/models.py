"""
Models for the organization application
"""

# Django
from django.db import models
from django.db.models.expressions import F
from django.db.models.functions import Greatest
from django.utils.translation import gettext_lazy as _

# Standard Library
import logging

# Third Party
from squarelet_auth.organizations.models import AbstractOrganization

# DocumentCloud
from documentcloud.core.choices import Language
from documentcloud.organizations.querysets import OrganizationQuerySet

logger = logging.getLogger(__name__)


class Organization(AbstractOrganization):
    """An orginization users can belong to"""

    objects = OrganizationQuerySet.as_manager()

    pages_per_month = models.IntegerField(
        _("pages per month"),
        default=0,
        help_text=_("How many monthly pages this organization gets each month"),
    )
    monthly_pages = models.IntegerField(
        _("monthly pages"),
        default=0,
        help_text=_(
            "How many recurring monthly pages are left for this month - these do "
            "not roll over and are just reset to `pages_per_month` on `date_update`"
        ),
    )
    number_pages = models.IntegerField(
        _("number pages"),
        default=0,
        help_text=_(
            "How many individually purchased pages this organization has - "
            "these never expire and are unaffected by the monthly roll over"
        ),
    )

    language = models.CharField(
        _("language"),
        max_length=3,
        choices=Language.choices,
        default="eng",
        blank=True,
        help_text=_("The default interface language for user's in this organization"),
    )
    document_language = models.CharField(
        _("document language"),
        max_length=3,
        choices=Language.choices,
        default="eng",
        blank=True,
        help_text=_("The default document language for user's in this organization"),
    )

    def __str__(self):
        if self.individual:
            return f"{self.name} (Individual)"
        else:
            return self.name

    @property
    def display_name(self):
        """Display 'Personal Account' for individual organizations"""
        if self.individual:
            return "Personal Account"
        else:
            return self.name

    def has_member(self, user):
        """Is the user a member of this organization?"""
        return self.users.filter(pk=user.pk).exists()

    def has_admin(self, user):
        """Is the user an admin of this organization?"""
        return self.users.filter(pk=user.pk, memberships__admin=True).exists()

    def _update_resources(self, data, date_update):
        # calc reqs/month in case it has changed
        self.pages_per_month = self.calc_pages_per_month(data["max_users"])

        # if date update has changed, then this is a monthly restore of the
        # subscription, and we should restore monthly pages.  If not, pages
        # per month may have changed if they changed their plan or their user count,
        # in which case we should add the difference to their monthly pages
        # if pages per month increased
        if self.date_update == date_update:
            # add additional monthly pages immediately
            self.monthly_pages = F("monthly_pages") + Greatest(
                self.pages_per_month - F("pages_per_month"), 0
            )
        else:
            # reset monthly pages when date_update is updated
            self.monthly_pages = self.pages_per_month
            self.date_update = date_update

    def _choose_entitlement(self, entitlements):
        return max(entitlements, key=lambda e: e["resources"].get("base_pages", 0))

    def calc_pages_per_month(self, users):
        """Calculate how many pages an organization gets per month on this plan
        for a given number of users"""
        return (
            self.entitlement.base_pages
            + (users - self.entitlement.minimum_users) * self.entitlement.pages_per_user
        )
