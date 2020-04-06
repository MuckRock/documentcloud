"""Custom querysets for users app"""

# Django
from django.db import models
from django.db.models import Prefetch, Q

# DocumentCloud
from documentcloud.organizations.models import Membership


class UserQuerySet(models.QuerySet):
    """Custom queryset for users"""

    def get_viewable(self, user):
        """You may view other users in your organizations and projects"""
        if user.is_authenticated:
            return self.filter(
                Q(organizations__in=user.organizations.all())
                | Q(projects__in=user.projects.all())
            ).distinct()
        else:
            return self.none()

    def preload(self, _user, _expand):
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
