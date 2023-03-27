"""Custom querysets for entities app"""

# Django
from django.db import models
from django.db.models import Q

# DocumentCloud
from documentcloud.entities.choices import EntityAccess


class EntityQuerySet(models.QuerySet):
    """Custom queryset for entities"""

    def get_viewable(self, user):
        if user.is_authenticated:
            return self.filter(Q(user=user) | Q(access=EntityAccess.public))
        else:
            return self.filter(access=EntityAccess.public)
