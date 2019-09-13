"""Custom querysets for document app"""

# Django
from django.db import models
from django.db.models import Q

# DocumentCloud
from documentcloud.documents.choices import Access


class DocumentQuerySet(models.QuerySet):
    """Custom queryset for documents"""

    def get_viewable(self, user):
        if user.is_authenticated:
            query = (
                # you may see public documents
                Q(access=Access.public)
                # you can see documents you own
                | Q(user=user)
                # you may see documents in your projects
                # | Q(projects__collaborators=user)
                # you can see organization level documents in your
                # organization if you are not a freelancer
                # XXX freelancer
                | Q(access=Access.organization, organization=user.organization)
            )
            return self.exclude(access=Access.invisible).filter(query)
        else:
            return self.filter(access=Access.public)
