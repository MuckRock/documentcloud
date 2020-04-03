"""Custom querysets for project app"""

# Django
from django.db import models
from django.db.models import Q
from django.db.models.expressions import OuterRef, Subquery, Value
from django.db.models.fields import BooleanField
from django.db.models.functions import Cast
from django.db.models.query import Prefetch

# Third Party
from rest_flex_fields.utils import split_levels

# DocumentCloud
from documentcloud.documents.models import Document
from documentcloud.projects.choices import CollaboratorAccess
from documentcloud.users.models import User


class ProjectQuerySet(models.QuerySet):
    """Custom queryset for projects"""

    def get_viewable(self, user):
        if user.is_authenticated:
            return self.filter(Q(private=False) | Q(collaborators=user)).distinct()
        else:
            return self.filter(private=False)

    def annotate_is_admin(self, user):
        """Annotate each project with whether or not the given user is
        an admin for it
        """
        if user.is_authenticated:
            return self.annotate(
                is_admin=Cast(
                    Subquery(
                        user.collaboration_set.filter(
                            project_id=OuterRef("pk"), access=CollaboratorAccess.admin
                        )
                        .values("pk")
                        .order_by()
                    ),
                    output_field=BooleanField(),
                )
            )
        else:
            return self.annotate(is_admin=Value(False, output_field=BooleanField()))


class ProjectMembershipQuerySet(models.QuerySet):
    """Custom queryset for project memberships"""

    def get_viewable(self, user):
        return self.filter(document__in=Document.objects.get_viewable(user))

    def preload(self, user, expand):
        """Preload relations"""
        queryset = self
        top_expands, nested_expands = split_levels(expand)
        all_expanded = "~all" in top_expands
        nested_default = "~all" if all_expanded else ""

        if "document" in top_expands or all_expanded:
            queryset = queryset.prefetch_related(
                Prefetch(
                    "document",
                    queryset=Document.objects.preload(
                        user, nested_expands.get("document", nested_default)
                    ),
                )
            )

        return queryset


class CollaborationQuerySet(models.QuerySet):
    """Custom queryset for collaborations"""

    def preload(self, user, expand):
        """Preload relations"""
        queryset = self
        top_expands, nested_expands = split_levels(expand)
        all_expanded = "~all" in top_expands
        nested_default = "~all" if all_expanded else ""

        if "user" in top_expands or all_expanded:
            queryset = queryset.prefetch_related(
                Prefetch(
                    "user",
                    queryset=User.objects.preload(
                        user, nested_expands.get("user", nested_default)
                    ),
                )
            )

        return queryset
