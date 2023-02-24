"""Custom querysets for entities app"""

# Django
from django.db import models
from django.db.models import Q

# Third Party
from parler.managers import TranslatableQuerySet

# DocumentCloud
from documentcloud.entities.choices import EntityAccess


class EntityQuerySet(TranslatableQuerySet):
    """Custom queryset for entities"""

    def get_viewable(self, user):
        if user.is_authenticated:
            return self.filter(Q(user=user) | Q(access=EntityAccess.public))
        else:
            return self.filter(access=EntityAccess.public)
