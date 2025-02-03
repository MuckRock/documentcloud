# Django
from django.db import transaction
from django.db.models import Q
from django.db.models.expressions import Exists, OuterRef, Value
from django.utils import timezone
from django.utils.decorators import method_decorator
from rest_framework import exceptions, filters, serializers, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import SAFE_METHODS

# Standard Library
from functools import lru_cache

# Third Party
import django_filters
from django_filters.rest_framework.backends import DjangoFilterBackend
from rest_flex_fields.views import FlexFieldsModelViewSet

# DocumentCloud
from documentcloud.core.filters import ModelMultipleChoiceFilter
from documentcloud.core.pagination import VersionedCountPagination
from documentcloud.core.permissions import (
    DjangoObjectPermissionsOrAnonReadOnly,
    ProjectPermissions,
)
from documentcloud.documents.decorators import (
    anonymous_cache_control,
    conditional_cache_control,
)
from documentcloud.documents.models import Document
from documentcloud.documents.views import DocumentViewSet
from documentcloud.drf_bulk.views import BulkModelMixin
from documentcloud.projects.choices import CollaboratorAccess
from documentcloud.projects.models import Collaboration, Project, ProjectMembership
from documentcloud.projects.serializers import (
    CollaborationSerializer,
    ProjectMembershipSerializer,
    ProjectSerializer,
)
from documentcloud.users.models import User


def _solr_set(document):
    """Set the projects and projects_edit_access fields in solr after altering the
    project memberships
    """
    field_updates = {"projects": "set", "projects_edit_access": "set"}
    document.index_on_commit(field_updates=field_updates)


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    queryset = Project.objects.none()

    def get_queryset(self):
        queryset = Project.objects.get_viewable(self.request.user).annotate_is_admin(
            self.request.user
        )
        if self.request.user.is_authenticated:
            queryset = queryset.annotate(
                pinned=Exists(
                    self.request.user.pinned_projects.filter(pk=OuterRef("pk"))
                )
            )
        else:
            queryset = queryset.annotate(pinned=Value(False))
        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        """Specify the creator, add them as a collaborator by default, and
        pin the project for them
        """
        project = serializer.save(user=self.request.user)
        Collaboration.objects.create(
            project=project,
            user=self.request.user,
            creator=self.request.user,
            access=CollaboratorAccess.admin,
        )
        self.request.user.pinned_projects.add(project)

    @transaction.atomic
    def perform_destroy(self, instance):
        """When destroying a project, make sure we remove all of its documents
        from the project on solr
        """
        # get all of the project memberships for this project
        project_memberships = instance.projectmembership_set.all().select_related(
            "document"
        )
        # set solr dirty and updated at for all of the documents in this project
        Document.objects.filter(
            pk__in=[pm.document.pk for pm in project_memberships]
        ).update(solr_dirty=True, updated_at=timezone.now())
        # remove the documents from the project on solr
        for project_membership in project_memberships:
            _solr_set(project_membership.document)

        super().perform_destroy(instance)

    def perform_update(self, serializer):

        project = self.get_object()
        # fields anyone may edit
        allowed_public_edits = ["pinned"]

        if not self.request.user.has_perm("projects.change_project_all", project):
            for datum in serializer.initial_data:
                if datum not in allowed_public_edits:
                    raise exceptions.PermissionDenied(
                        "You do not have permission to edit this document"
                    )

        super().perform_update(serializer)
        # add or remove project from the current user's pinned projects
        # if needed
        if "pinned_w" not in serializer.validated_data:
            return
        if serializer.validated_data["pinned_w"] and not project.pinned:
            self.request.user.pinned_projects.add(project)
        if not serializer.validated_data["pinned_w"] and project.pinned:
            self.request.user.pinned_projects.remove(project)
        # pylint: disable=pointless-statement, protected-access
        # data is a property, we call it here to populate _data
        serializer.data
        # we need to set _data directly to set the update value from pinned
        serializer._data["pinned"] = serializer.validated_data["pinned_w"]

    class Filter(django_filters.FilterSet):
        user = ModelMultipleChoiceFilter(model=User, field_name="collaborators", help_text="Filter by projects where this user is a collaborator")
        document = ModelMultipleChoiceFilter(model=Document, field_name="documents", help_text="Filter by projects which contain the given document")
        query = django_filters.CharFilter(method="query_filter", label="Query", help_text="")
        pinned = django_filters.BooleanFilter(field_name="pinned", label="Pinned", help_text="Filters by whether this project has been pinned by the user")
        is_shared = django_filters.BooleanFilter(
            method="filter_is_shared", label="Shared", help_text="Filter projects by whether they are shared with the currently logged in user. Excludes projects the user owns."
        )
        owned_by_user = django_filters.BooleanFilter(
            method="filter_owned_by_user", label="Owned", help_text="Filter projects by whether the currently logged in user owns the project or not. Excludes projects shared with the user as a collaborator. "
        )
        private = django_filters.BooleanFilter(field_name="private", help_text="Whether the project is private or not")
        slug = django_filters.CharFilter(field_name="slug", help_text="Filter by the slug, a URL safe version of the title")
        title = django_filters.CharFilter(field_name="title", help_text="Filters by the title of the project")
        class Meta:
            model = Project
            fields = {
                "user": ["exact"],
                # "document": ["exact"],
                "private": ["exact"],
                "slug": ["exact"],
                "title": ["exact"],
                "id": ["in"],
            }

        def query_filter(self, queryset, name, value):
            # pylint: disable=unused-argument
            return queryset.filter(
                Q(title__icontains=value) | Q(description__icontains=value)
            )

        def filter_is_shared(self, queryset, _name, value):
            """Filter projects shared with user, but not owned"""
            if value and self.request.user.is_authenticated:
                return queryset.filter(
                    Q(collaborators=self.request.user) & ~Q(user=self.request.user)
                )
            return queryset

        def filter_owned_by_user(self, queryset, _name, value):
            """Filter projects where the user is the owner."""
            if value and self.request.user.is_authenticated:
                return queryset.filter(user=self.request.user)
            return queryset

    filterset_class = Filter


class OrderingFilter(filters.OrderingFilter):
    filter_map = {
        "created_at": "document__pk",
        "-created_at": "-document__pk",
    }

    def get_ordering(self, request, queryset, view):
        param = request.query_params.get(self.ordering_param)

        if param in self.filter_map:
            return [self.filter_map[param]]

        # No ordering was included
        return self.get_default_ordering(view)

    def filter_queryset(self, request, queryset, view):
        ordering = self.get_ordering(request, queryset, view)

        if ordering:
            distinct = [o.lstrip("-") for o in ordering]
            return queryset.order_by(*ordering).distinct(*distinct)

        return queryset


@method_decorator(conditional_cache_control(no_cache=True), name="dispatch")
@method_decorator(anonymous_cache_control, name="list")
class ProjectMembershipViewSet(BulkModelMixin, FlexFieldsModelViewSet):
    serializer_class = ProjectMembershipSerializer
    queryset = ProjectMembership.objects.none()
    lookup_field = "document_id"
    permit_list_expands = ["document"] + [
        f"document.{e}" for e in DocumentViewSet.permit_list_expands
    ]
    permission_classes = (DjangoObjectPermissionsOrAnonReadOnly | ProjectPermissions,)
    pagination_class = VersionedCountPagination
    filter_backends = [OrderingFilter, DjangoFilterBackend]
    ordering_fields = ["created_at"]
    ordering = ["-document__pk"]

    @lru_cache()
    def get_queryset(self):
        """Only fetch projects viewable to this user"""
        valid_token = (
            hasattr(self.request, "auth")
            and self.request.auth is not None
            and "processing" in self.request.auth.get("permissions", [])
        )
        if valid_token:
            # Processing scope can access all projects
            queryset = Project.objects.all()
        else:
            queryset = Project.objects.get_viewable(self.request.user)

        project = get_object_or_404(queryset, pk=self.kwargs["project_pk"])

        if valid_token:
            # Processing scope can access all documents
            queryset = project.projectmembership_set.all()
        else:
            queryset = project.projectmembership_set.get_viewable(self.request.user)

        return queryset.preload(
            self.request.user, self.request.query_params.get("expand", "")
        )

    @lru_cache()
    def check_edit_project(self):
        project = Project.objects.get(pk=self.kwargs["project_pk"])
        if not self.request.user.has_perm("projects.add_remove_project", project):
            raise exceptions.PermissionDenied(
                "You do not have permission to edit documents in this project"
            )

    def check_permissions(self, request):
        """Add an additional check that you can edit to the project before
        allowing the user to change a document within a project
        """
        super().check_permissions(request)
        if request.method not in SAFE_METHODS:
            self.check_edit_project()

    @transaction.atomic
    def perform_create(self, serializer):
        """Specify the project"""
        project = Project.objects.get(pk=self.kwargs["project_pk"])
        serializer.save(project=project)

        if hasattr(serializer, "many") and serializer.many:
            validated_datas = serializer.validated_data
        else:
            validated_datas = [serializer.validated_data]

        Document.objects.filter(
            pk__in=[d["document"].pk for d in validated_datas]
        ).update(solr_dirty=True, updated_at=timezone.now())
        for data in validated_datas:
            _solr_set(data["document"])

    @transaction.atomic
    def perform_update(self, serializer):
        super().perform_update(serializer)

        if hasattr(serializer, "many") and serializer.many:
            validated_datas = serializer.validated_data
        else:
            # if we are updating a single instance, the document is specified
            # in the url instead of in the payload, so add it back in
            serializer.validated_data["document"] = Document.objects.get(
                pk=self.kwargs["document_id"]
            )
            validated_datas = [serializer.validated_data]

        Document.objects.filter(
            pk__in=[d["document"].pk for d in validated_datas]
        ).update(solr_dirty=True, updated_at=timezone.now())
        for data in validated_datas:
            _solr_set(data["document"])

    @transaction.atomic
    def bulk_perform_update(self, serializer, partial):
        # a non-partial bulk update will create and destroy memberships in the project
        # to fully match the list of documents passed in
        # a partial bulk update will only create new memberships passed in

        membership_mapping = {m.document: m for m in serializer.instance}
        data_mapping = {item["document"]: item for item in serializer.validated_data}

        # mark all updated documents as solr dirty
        if partial:
            updated_docs = data_mapping.keys()
        else:
            updated_docs = membership_mapping.keys() | data_mapping.keys()
        Document.objects.filter(pk__in=[d.pk for d in updated_docs]).update(
            solr_dirty=True, updated_at=timezone.now()
        )
        # create new memberships and update existing memberships
        memberships = []
        for document, data in data_mapping.items():
            membership = membership_mapping.get(document)
            if membership is None:
                # add the project id into the data before creating
                data["project_id"] = self.kwargs["project_pk"]
                memberships.append(serializer.child.create(data))
                _solr_set(data["document"])
            else:
                memberships.append(serializer.child.update(membership, data))
                _solr_set(data["document"])

        # delete existing memberships not present in the data, if not partial
        if not partial:
            delete = [
                (d, m) for d, m in membership_mapping.items() if d not in data_mapping
            ]
            ProjectMembership.objects.filter(
                pk__in=[m.pk for (_, m) in delete]
            ).delete()
            for document, _ in delete:
                _solr_set(document)

        return memberships

    @transaction.atomic
    def bulk_perform_destroy(self, objects):
        Document.objects.filter(pk__in=[o.document.pk for o in objects]).update(
            solr_dirty=True, updated_at=timezone.now()
        )
        ProjectMembership.objects.filter(pk__in=[o.pk for o in objects]).delete()
        for obj in objects:
            _solr_set(obj.document)

    @transaction.atomic
    def perform_destroy(self, instance):
        instance.document.solr_dirty = True
        instance.document.save()
        super().perform_destroy(instance)
        _solr_set(instance.document)

    class Filter(django_filters.FilterSet):
        document_id__in = ModelMultipleChoiceFilter(
            model=Document, field_name="document"
        )

        class Meta:
            model = ProjectMembership
            fields = ["document_id__in"]

    filterset_class = Filter


class CollaborationViewSet(FlexFieldsModelViewSet):
    serializer_class = CollaborationSerializer
    queryset = Collaboration.objects.none()
    lookup_field = "user_id"
    permit_list_expands = ["user", "user.organization"]

    @lru_cache()
    def get_queryset(self):
        """Only fetch projects viewable to this user"""
        project = get_object_or_404(
            Project.objects.get_viewable(self.request.user),
            pk=self.kwargs["project_pk"],
        )
        if self.request.user.has_perm("projects.change_project_all", project):
            queryset = project.collaboration_set.all()
        else:
            queryset = project.collaboration_set.none()

        return queryset.preload(
            self.request.user, self.request.query_params.get("expand", "")
        )

    def perform_create(self, serializer):
        """Specify the project"""
        project = Project.objects.get(pk=self.kwargs["project_pk"])
        if not self.request.user.has_perm("projects.change_project_all", project):
            raise exceptions.PermissionDenied(
                "You do not have permission to add collaborators to this project"
            )

        serializer.save(project=project, creator=self.request.user)

    def destroy(self, request, *args, **kwargs):
        project = Project.objects.get(pk=self.kwargs["project_pk"])
        collaboration = self.get_object()
        if (
            collaboration.access == CollaboratorAccess.admin
            and project.collaboration_set.filter(
                access=CollaboratorAccess.admin
            ).count()
            == 1
        ):
            raise serializers.ValidationError(
                "May not remove the only admin from a project"
            )
        return super().destroy(request, *args, **kwargs)
