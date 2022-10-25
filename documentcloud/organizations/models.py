"""
Models for the organization application
"""

# Django
from django.db import models, transaction
from django.db.models.expressions import F
from django.db.models.functions import Greatest
from django.utils.translation import gettext_lazy as _

# Standard Library
import logging

# Third Party
from squarelet_auth.organizations.models import AbstractOrganization

# DocumentCloud
from documentcloud.core.choices import Language
from documentcloud.organizations.exceptions import InsufficientAICreditsError
from documentcloud.organizations.querysets import OrganizationQuerySet

logger = logging.getLogger(__name__)


class Organization(AbstractOrganization):
    """An orginization users can belong to"""

    objects = OrganizationQuerySet.as_manager()

    ai_credits_per_month = models.IntegerField(
        _("AI credits per month"),
        default=0,
        help_text=_("How many monthly AI credits this organization gets each month"),
    )
    monthly_ai_credits = models.IntegerField(
        _("monthly AI credits"),
        default=0,
        help_text=_(
            "How many recurring monthly AI credits are left for this month - these do "
            "not roll over and are just reset to `ai_credits_per_month` on "
            "`date_update`"
        ),
    )
    number_ai_credits = models.IntegerField(
        _("number AI credits"),
        default=0,
        help_text=_(
            "How many individually purchased AI credits this organization has - "
            "these never expire and are unaffected by the monthly roll over"
        ),
    )

    language = models.CharField(
        _("language"),
        max_length=8,
        choices=Language.choices,
        default="eng",
        blank=True,
        help_text=_("The default interface language for user's in this organization"),
    )
    document_language = models.CharField(
        _("document language"),
        max_length=8,
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
        self.ai_credits_per_month = self.calc_ai_credits_per_month(data["max_users"])

        # if date update has changed, then this is a monthly restore of the
        # subscription, and we should restore monthly AI credits.  If not, AI credits
        # per month may have changed if they changed their plan or their user count,
        # in which case we should add the difference to their monthly AI credits
        # if AI credits per month increased
        if self.date_update == date_update:
            # add additional monthly AI credits immediately
            self.monthly_ai_credits = F("monthly_ai_credits") + Greatest(
                self.ai_credits_per_month - F("ai_credits_per_month"), 0
            )
        else:
            # reset monthly AI credits when date_update is updated
            self.monthly_ai_credits = self.ai_credits_per_month
            self.date_update = date_update

    def _choose_entitlement(self, entitlements):
        return max(entitlements, key=lambda e: e["resources"].get("base_ai_credits", 0))

    def calc_ai_credits_per_month(self, users):
        """Calculate how many AI credits an organization gets per month on this plan
        for a given number of users"""
        return (
            self.entitlement.base_ai_credits
            + (users - self.entitlement.minimum_users)
            * self.entitlement.ai_credits_per_user
        )

    @transaction.atomic
    def use_ai_credits(self, amount):
        """Try to deduct AI credits from the organization's balance"""
        ai_credit_count = {"monthly": 0, "regular": 0}
        organization = Organization.objects.select_for_update().get(pk=self.pk)

        ai_credit_count["monthly"] = min(amount, organization.monthly_ai_credits)
        amount -= ai_credit_count["monthly"]

        ai_credit_count["regular"] = min(amount, organization.number_ai_credits)
        amount -= ai_credit_count["regular"]

        if amount > 0:
            raise InsufficientAICreditsError(amount)

        organization.monthly_ai_credits -= ai_credit_count["monthly"]
        organization.number_ai_credits -= ai_credit_count["regular"]
        organization.save()
        return ai_credit_count
