# Django
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from rest_framework import exceptions, serializers, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import SAFE_METHODS

# Standard Library
from functools import lru_cache

# Third Party
import django_filters
from django_filters.constants import EMPTY_VALUES
from rest_flex_fields.views import FlexFieldsModelViewSet

# DocumentCloud
from documentcloud.core.filters import ModelMultipleChoiceFilter
from documentcloud.core.permissions import (
    DjangoObjectPermissionsOrAnonReadOnly,
    ProjectPermissions,
)
from documentcloud.documents.decorators import (
    anonymous_cache_control,
    conditional_cache_control,
)
from documentcloud.documents.models import Document
from documentcloud.documents.tasks import solr_index
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


def _solr_set(document_pk):
    """Set the projects and projects_edit_access fields in solr after altering the
    project memberships
    """
    field_updates = {"projects": "set", "projects_edit_access": "set"}
    transaction.on_commit(
        lambda: solr_index.delay(document_pk, field_updates=field_updates)
    )


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    queryset = Project.objects.none()

    def get_queryset(self):
        return Project.objects.get_viewable(self.request.user).annotate_is_admin(
            self.request.user
        )

    @transaction.atomic
    def perform_create(self, serializer):
        """Specify the creator and add them as a collaborator by default"""
        project = serializer.save(user=self.request.user)
        Collaboration.objects.create(
            project=project,
            user=self.request.user,
            creator=self.request.user,
            access=CollaboratorAccess.admin,
        )

    @transaction.atomic
    def perform_destroy(self, instance):
        """When destroying a project, make sure we remove all of its documents
        from the project on solr
        """
        # get all of the project memberships for this project
        project_memberships = instance.projectmembership_set.all()
        # set solr dirty and updated at for all of the documents in this project
        Document.objects.filter(
            pk__in=[pm.document.pk for pm in project_memberships]
        ).update(solr_dirty=True, updated_at=timezone.now())
        # remove the documents from the project on solr
        for project_membership in project_memberships:
            _solr_set(project_membership.document_id)

        super().perform_destroy(instance)

    class Filter(django_filters.FilterSet):
        user = ModelMultipleChoiceFilter(model=User, field_name="collaborators")
        document = ModelMultipleChoiceFilter(model=Document, field_name="documents")

        class Meta:
            model = Project
            fields = {
                "user": ["exact"],
                # "document": ["exact"],
                "private": ["exact"],
                "slug": ["exact"],
                "title": ["exact"],
            }

    filterset_class = Filter


class OrderingFilter(django_filters.OrderingFilter):
    """Always add PK to the order to ensure proper index usage
    Postgres is picking a much slower execution path in certain cases
    without this modification
    """

    def filter(self, qs, value):
        """Add PK to all orderings"""
        if value in EMPTY_VALUES:
            return qs

        ordering = [self.get_ordering_value(param) for param in value]
        ordering.append("pk")
        return qs.order_by(*ordering)


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

    @lru_cache()
    def get_queryset(self):
        """Only fetch projects viewable to this user"""
        valid_token = (
            hasattr(self.request, "auth")
            and self.request.auth is not None
            and "processing" in self.request.auth["permissions"]
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

        return (
            # adding ID to the order by here helps postgres pick an appropriate
            # execution plan and drastically reduces run time in certain cases
            queryset.preload(
                self.request.user, self.request.query_params.get("expand", "")
            ).order_by("-document__created_at", "id")
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
            _solr_set(data["document"].pk)

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
            _solr_set(data["document"].pk)

    @transaction.atomic
    def bulk_perform_update(self, serializer, partial):
        # for partial bulk updates, we simply update the data for each membership
        # passed in - we expect all memberships passed in to exist
        if partial:
            return self.perform_update(serializer)

        # a non-partial bulk update will create and destroy memberships in the project
        # to fully match the list of documents passed in
        membership_mapping = {m.document: m for m in serializer.instance}
        data_mapping = {item["document"]: item for item in serializer.validated_data}

        # mark all documents as solr dirty
        Document.objects.filter(
            pk__in=[d.pk for d in membership_mapping.keys() | data_mapping.keys()]
        ).update(solr_dirty=True, updated_at=timezone.now())
        # create new memberships and update existing memberships
        memberships = []
        for document, data in data_mapping.items():
            membership = membership_mapping.get(document)
            if membership is None:
                # add the project id into the data before creating
                data["project_id"] = self.kwargs["project_pk"]
                memberships.append(serializer.child.create(data))
                _solr_set(data["document"].pk)
            else:
                memberships.append(serializer.child.update(membership, data))
                _solr_set(data["document"].pk)

        # delete existing memberships not present in the data
        delete = [m for d, m in membership_mapping.items() if d not in data_mapping]
        ProjectMembership.objects.filter(pk__in=[m.pk for m in delete]).delete()
        for membership in delete:
            _solr_set(membership.document_id)

        return memberships

    @transaction.atomic
    def bulk_perform_destroy(self, objects):
        Document.objects.filter(pk__in=[o.document.pk for o in objects]).update(
            solr_dirty=True, updated_at=timezone.now()
        )
        ProjectMembership.objects.filter(pk__in=[o.pk for o in objects]).delete()
        for obj in objects:
            _solr_set(obj.document_id)

    @transaction.atomic
    def perform_destroy(self, instance):
        instance.document.solr_dirty = True
        instance.document.save()
        super().perform_destroy(instance)
        _solr_set(instance.document_id)

    class Filter(django_filters.FilterSet):
        ordering = OrderingFilter(
            fields=(
                ("document__created_at", "created_at"),
                ("document__page_count", "page_count"),
                ("document__title", "title"),
                ("document__source", "source"),
            )
        )
        document_id__in = ModelMultipleChoiceFilter(
            model=Document, field_name="document"
        )

        class Meta:
            model = ProjectMembership
            fields = ["document_id__in"]
            order_by = ("created_at", "page_count")

        def get_ordering(self, order_choice):
            return [order_choice, "pk"]

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
        if self.request.user.has_perm("projects.change_project", project):
            queryset = project.collaboration_set.all()
        else:
            queryset = project.collaboration_set.none()

        return queryset.preload(
            self.request.user, self.request.query_params.get("expand", "")
        )

    def perform_create(self, serializer):
        """Specify the project"""
        project = Project.objects.get(pk=self.kwargs["project_pk"])
        if not self.request.user.has_perm("projects.change_project", project):
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
