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

    # pylint: disable=too-many-instance-attributes

    objects = OrganizationQuerySet.as_manager()

    uuid = models.UUIDField(
        "UUID", unique=True, editable=False, default=uuid4, db_index=True
    )

    users = models.ManyToManyField(
        "users.User", through="organizations.Membership", related_name="organizations"
    )

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    private = models.BooleanField(default=False)
    individual = models.BooleanField(default=True)
    plan = models.ForeignKey("organizations.Plan", on_delete=models.PROTECT, null=True)
    card = models.CharField(max_length=255, blank=True)
    avatar_url = models.URLField(max_length=255, blank=True)

    pages_per_month = models.IntegerField(
        default=0,
        help_text=_("How many monthly pages this organization gets each month"),
    )
    monthly_pages = models.IntegerField(
        default=0,
        help_text=_(
            "How many recurring monthly pages are left for this month - these do "
            "not roll over and are just reset to `pages_per_month` on `date_update`"
        ),
    )
    number_pages = models.IntegerField(
        default=0,
        help_text=_(
            "How many individually purchased pages this organization has - "
            "these never expire and are unaffected by the monthly roll over"
        ),
    )
    date_update = models.DateField(null=True)

    payment_failed = models.BooleanField(default=False)

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
        "users.User", on_delete=models.CASCADE, related_name="memberships"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    active = models.BooleanField(default=False)
    admin = models.BooleanField(default=False)

    class Meta:
        unique_together = ("user", "organization")

    def __str__(self):
        return f"{self.user} in {self.organization}"


class Plan(models.Model):
    """Plans that organizations can subscribe to"""

    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True)

    minimum_users = models.PositiveSmallIntegerField(default=1)
    base_pages = models.PositiveSmallIntegerField(default=0)
    pages_per_user = models.PositiveSmallIntegerField(default=0)
    feature_level = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return self.name

    def pages_per_month(self, users):
        """Calculate how many pages an organization gets per month on this plan
        for a given number of users"""
        return self.base_pages + (users - self.minimum_users) * self.pages_per_user
