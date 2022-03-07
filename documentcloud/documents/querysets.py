"""Custom querysets for document app"""

# Django
from django.db import models
from django.db.models import Q
from django.db.models.query import Prefetch

# Third Party
from rest_flex_fields.utils import split_levels

# DocumentCloud
from documentcloud.documents.choices import Access, Status
from documentcloud.projects.choices import CollaboratorAccess
from documentcloud.users.models import User


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
                | Q(
                    projects__in=user.projects.all(),
                    projectmembership__edit_access=True,
                )
                # you can see organization level documents in your
                # organization
                | Q(
                    access=Access.organization,
                    organization__in=user.organizations.all(),
                )
            )
            return (
                self.exclude(access=Access.invisible)
                .exclude(status=Status.deleted)
                .filter(query)
                .distinct("id")
            )
        else:
            return self.filter(
                access=Access.public, status__in=[Status.success, Status.readable]
            )

    def get_editable(self, user):
        if user.is_authenticated:
            # only get the user's projects where they have edit access
            projects = user.projects.filter(
                collaboration__access__in=(
                    CollaboratorAccess.admin,
                    CollaboratorAccess.edit,
                )
            )
            query = (
                # you can edit documents you own that are not public
                (Q(user=user) & ~Q(access=Access.public))
                # you may edit documents in your projects shared for editing
                | (
                    Q(projects__in=projects, projectmembership__edit_access=True)
                    & ~Q(access=Access.public)
                )
                # you can edit organization level documents in your
                # organization
                | Q(
                    access__in=(Access.organization, Access.public),
                    organization__in=user.organizations.all(),
                )
            )
            return (
                self.exclude(access=Access.invisible)
                .exclude(status=Status.deleted)
                .filter(query)
                .distinct("id")
            )
        else:
            return self.none()

    def preload(self, user, expand):
        """Preload relations"""
        from documentcloud.projects.models import Project

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
        else:
            queryset = queryset.select_related("user")

        if "organization" in top_expands or all_expanded:
            queryset = queryset.select_related("organization")

        if "projects" in top_expands or all_expanded:
            projects = Project.objects.annotate_is_admin(user)
        else:
            projects = Project.objects.all()
        queryset = queryset.prefetch_related(
            Prefetch("projects", projects.get_viewable(user))
        )

        if "sections" in top_expands or all_expanded:
            queryset = queryset.prefetch_related("sections")

        return queryset


class NoteQuerySet(models.QuerySet):
    """Custom queryset for notes"""

    def get_viewable(self, user, document):
        if user.is_authenticated:
            can_change = user.has_perm("documents.change_document", document)
            query = (
                # you may see public notes
                Q(access=Access.public)
                # you can see notes you own
                | Q(user=user)
            )
            # if you have edit access for the document, you can view collab (org) notes
            if can_change:
                query |= Q(access=Access.organization)
            return self.filter(query, document=document).exclude(
                access=Access.invisible
            )
        else:
            return self.filter(access=Access.public, document=document)

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
        else:
            queryset = queryset.select_related("user")

        if "organization" in top_expands or all_expanded:
            queryset = queryset.select_related("organization")

        return queryset
