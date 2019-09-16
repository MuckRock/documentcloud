"""
Models for the organization application
"""

# Django
from django.db import models
from django.db.models.expressions import F
from django.db.models.functions import Greatest
from django.utils.translation import ugettext_lazy as _

# Standard Library
import logging
from uuid import uuid4

# DocumentCloud
from documentcloud.organizations.querysets import OrganizationQuerySet

logger = logging.getLogger(__name__)


class Organization(models.Model):
    """An orginization users can belong to"""

    objects = OrganizationQuerySet.as_manager()

    uuid = models.UUIDField(
        _("UUID"),
        unique=True,
        editable=False,
        default=uuid4,
        db_index=True,
        help_text=_("Unique ID to link organizations across MuckRock's sites"),
    )

    users = models.ManyToManyField(
        verbose_name=_("users"),
        to="users.User",
        through="organizations.Membership",
        related_name="organizations",
        help_text=_("The users who are members of this organization"),
    )

    name = models.CharField(
        _("name"), max_length=255, help_text=_("Name of the organization")
    )
    slug = models.SlugField(
        _("slug"),
        max_length=255,
        unique=True,
        help_text=_("Unique slug for the organization which may be used in a URL"),
    )
    private = models.BooleanField(
        _("private"),
        default=False,
        help_text=_(
            "Whether or not to keep this organization and its membership list private"
        ),
    )
    individual = models.BooleanField(
        _("individual"),
        default=True,
        help_text=_("Is this an organization for an individual user?"),
    )
    plan = models.ForeignKey(
        verbose_name=_("plan"),
        to="organizations.Plan",
        on_delete=models.PROTECT,
        null=True,
        help_text=_("The subscription type for this organization"),
    )
    card = models.CharField(
        _("card"),
        max_length=255,
        blank=True,
        help_text=_(
            "The brand and last 4 digits of the default credit card on file for this "
            "organization, for display purposes"
        ),
    )
    avatar_url = models.URLField(
        _("avatar url"),
        max_length=255,
        blank=True,
        help_text=_("A URL which points to an avatar for the organization"),
    )

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
    date_update = models.DateField(
        _("date update"),
        null=True,
        help_text=_("The date when this organizations monthly pages will be refreshed"),
    )

    payment_failed = models.BooleanField(
        _("payment failed"),
        default=False,
        help_text=_(
            "This organizations payment method has failed and should be updated"
        ),
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

    def update_data(self, data):
        """Set updated data from squarelet"""

        # plan should always be created on client sites before being used
        # get_or_create is used as a precauitionary measure
        self.plan, created = Plan.objects.get_or_create(
            slug=data["plan"], defaults={"name": data["plan"].replace("-", " ").title()}
        )
        if created:
            logger.warning("Unknown plan: %s", data["plan"])

        # calc reqs/month in case it has changed
        self.pages_per_month = self.plan.pages_per_month(data["max_users"])

        # if date update has changed, then this is a monthly restore of the
        # subscription, and we should restore monthly pages.  If not, pages
        # per month may have changed if they changed their plan or their user count,
        # in which case we should add the difference to their monthly pages
        # if pages per month increased
        if self.date_update == data["date_update"]:
            # add additional monthly pages immediately
            self.monthly_pages = F("monthly_pages") + Greatest(
                self.pages_per_month - F("pages_per_month"), 0
            )
        else:
            # reset monthly pages when date_update is updated
            self.monthly_pages = self.pages_per_month

        # update the remaining fields
        fields = [
            "name",
            "slug",
            "individual",
            "private",
            "date_update",
            "card",
            "payment_failed",
            "avatar_url",
        ]
        for field in fields:
            if field in data:
                setattr(self, field, data[field])
        self.save()


class Membership(models.Model):
    """Through table for organization membership"""

    user = models.ForeignKey(
        verbose_name=_("user"),
        to="users.User",
        on_delete=models.CASCADE,
        related_name="memberships",
        help_text=_("A user being linked to an organization"),
    )
    organization = models.ForeignKey(
        verbose_name=_("organization"),
        to="organizations.Organization",
        on_delete=models.CASCADE,
        related_name="memberships",
        help_text=_("An organization being linked to a user"),
    )
    active = models.BooleanField(
        _("active"),
        default=False,
        help_text=_("The user is currently working on behalf of this organization"),
    )
    admin = models.BooleanField(
        _("admin"),
        default=False,
        help_text=_("The user is an administrator for this organization"),
    )

    class Meta:
        unique_together = ("user", "organization")

    def __str__(self):
        return f"{self.user} in {self.organization}"


class Plan(models.Model):
    """Plans that organizations can subscribe to"""

    name = models.CharField(_("name"), max_length=255, unique=True)
    slug = models.SlugField(_("slug"), max_length=255, unique=True)

    minimum_users = models.PositiveSmallIntegerField(
        _("minimum users"),
        default=1,
        help_text=_("The minimum number of users included with this plan"),
    )
    base_pages = models.PositiveSmallIntegerField(
        _("base pages"),
        default=0,
        help_text=_("The number of monthly pages included by default with this plan"),
    )
    pages_per_user = models.PositiveSmallIntegerField(
        _("pages per user"),
        default=0,
        help_text=_(
            "The number of additional pages per month included with this plan for each "
            "user over the minimum"
        ),
    )
    feature_level = models.PositiveSmallIntegerField(
        _("feature level"),
        default=0,
        help_text=_("The level of premium features included with this plan"),
    )

    def __str__(self):
        return self.name

    def pages_per_month(self, users):
        """Calculate how many pages an organization gets per month on this plan
        for a given number of users"""
        return self.base_pages + (users - self.minimum_users) * self.pages_per_user
