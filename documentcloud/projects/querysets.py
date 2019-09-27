"""Custom querysets for project app"""

# Django
from django.db import models
from django.db.models import Q


class ProjectQuerySet(models.QuerySet):
    """Custom queryset for projects"""

    def get_viewable(self, user):
        if user.is_authenticated:
            return self.filter(Q(private=False) | Q(collaborators=user)).distinct()
        else:
            return self.filter(private=False)
