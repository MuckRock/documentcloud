"""Custom querysets for users app"""

# Django
from django.db import models
from django.db.models import Prefetch, Q

# DocumentCloud
from documentcloud.documents.choices import Access
from documentcloud.organizations.models import Membership


class UserQuerySet(models.QuerySet):
    """Custom queryset for users"""

    def get_viewable(self, user):
        """You may view other users in your organizations and projects,
        and anybody with a public document
        """
        if user.is_authenticated:
            return self.filter(
                Q(organizations__in=user.organizations.all())
                | Q(projects__in=user.projects.all())
                | Q(documents__access=Access.public)
            ).distinct()
        else:
            return self.filter(documents__access=Access.public).distinct()

    def preload(self, _user=None, _expand=""):
        """Preload relations"""
        queryset = self.prefetch_related(
            "organizations",
            Prefetch(
                "memberships",
                queryset=Membership.objects.filter(active=True).select_related(
                    "organization"
                ),
                to_attr="active_memberships",
            ),
        )

        return queryset
