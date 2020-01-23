"""Custom querysets for document app"""

# Django
from django.db import models
from django.db.models import Q

# DocumentCloud
from documentcloud.documents.choices import Access, Status


class DocumentQuerySet(models.QuerySet):
    """Custom queryset for documents"""

    def get_viewable(self, user):
        if user.is_authenticated:
            query = (
                # you may see public documents in a viewable state
                Q(access=Access.public, status__in=[Status.success, Status.readable])
                # you can see documents you own
                | Q(user=user)
                # you may see documents in your projects
                | Q(projects__collaborators=user)
                # you can see organization level documents in your
                # organization
                | Q(
                    access=Access.organization,
                    organization__in=user.organizations.all(),
                )
            )
            return self.exclude(access=Access.invisible).filter(query)
        else:
            return self.filter(
                access=Access.public, status__in=[Status.success, Status.readable]
            )


class NoteQuerySet(models.QuerySet):
    """Custom queryset for notes"""

    def get_viewable(self, user):
        if user.is_authenticated:
            return self.filter(
                # you may see public notes
                Q(access=Access.public)
                # you can see notes you own
                | Q(user=user)
                # you can see organization level notes in your organization
                | Q(
                    access=Access.organization,
                    organization__in=user.organizations.all(),
                )
            )
        else:
            return self.filter(access=Access.public)
