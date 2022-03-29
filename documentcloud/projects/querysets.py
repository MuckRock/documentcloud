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
from documentcloud.documents.choices import Access, Status
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

    def get_editable(self, user):
        if user.is_authenticated:
            return self.filter(
                collaborators=user, collaboration__access=CollaboratorAccess.admin
            )
        else:
            return self.none()

    def get_addable(self, user):
        """User may add or remove documents"""
        if user.is_authenticated:
            return self.filter(
                collaborators=user,
                collaboration__access__in=(
                    CollaboratorAccess.admin,
                    CollaboratorAccess.edit,
                ),
            )
        else:
            return self.none()

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
                ),
                is_editor=Cast(
                    Subquery(
                        user.collaboration_set.filter(
                            project_id=OuterRef("pk"),
                            access__in=[
                                CollaboratorAccess.admin,
                                CollaboratorAccess.edit,
                            ],
                        )
                        .values("pk")
                        .order_by()
                    ),
                    output_field=BooleanField(),
                ),
            )
        else:
            return self.annotate(is_admin=Value(False, output_field=BooleanField()))


class ProjectMembershipQuerySet(models.QuerySet):
    """Custom queryset for project memberships"""

    def get_viewable(self, user):
        if user.is_authenticated:

            query = (
                # you may see public documents in a viewable state
                Q(
                    document__access=Access.public,
                    document__status__in=[Status.success, Status.readable],
                )
                # you can see documents you own
                | Q(document__user=user)
                # you may see documents in your projects
                | Q(
                    document__projects__in=user.projects.all(),
                    document__projectmembership__edit_access=True,
                )
                # you can see organization level documents in your
                # organization
                | Q(
                    document__access=Access.organization,
                    document__organization__in=user.organizations.all(),
                )
            )
            return (
                self.exclude(document__access=Access.invisible)
                .exclude(document__status=Status.deleted)
                .filter(query)
                .distinct("id")
            )
        else:
            return self.filter(
                document__access=Access.public,
                document__status__in=[Status.success, Status.readable],
            )

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
