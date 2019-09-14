"""Custom querysets for users app"""

# Django
from django.db import models


class UserQuerySet(models.QuerySet):
    """Custom queryset for users"""

    def get_viewable(self, user):
        """You may view other users in your organization"""
        if user.is_authenticated:
            return self.filter(organizations__in=user.organizations.all()).distinct()
        else:
            return self.none()
