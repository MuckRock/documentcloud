"""Custom querysets for project app"""

# Django
from django.db import models
from django.db.models import Q

# DocumentCloud
from documentcloud.documents.models import Document


class ProjectQuerySet(models.QuerySet):
    """Custom queryset for projects"""

    def get_viewable(self, user):
        if user.is_authenticated:
            return self.filter(Q(private=False) | Q(collaborators=user)).distinct()
        else:
            return self.filter(private=False)


class ProjectMembershipQuerySet(models.QuerySet):
    """Custom queryset for project memberships"""

    def get_viewable(self, user):
        return self.filter(document__in=Document.objects.get_viewable(user))
