"""Custom querysets for organization app"""
# Django
from django.db import models, transaction
from django.db.models import Q

# Standard Library
from datetime import datetime


class OrganizationQuerySet(models.QuerySet):
    """Object manager for organizations"""

    def get_viewable(self, user):
        if user.is_authenticated:
            return self.filter(Q(users=user) | Q(private=False)).distinct()
        else:
            return self.filter(private=False)
