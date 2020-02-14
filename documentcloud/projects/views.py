# Django
from django.db import transaction
from rest_framework import exceptions, mixins, serializers, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import SAFE_METHODS

# Third Party
import django_filters
from rest_flex_fields.utils import is_expanded

# DocumentCloud
from documentcloud.core.filters import ModelMultipleChoiceFilter
from documentcloud.documents.models import Document
from documentcloud.documents.tasks import solr_index
from documentcloud.drf_bulk.views import BulkModelMixin
from documentcloud.projects.choices import CollaboratorAccess
from documentcloud.projects.models import Collaboration, Project, ProjectMembership
from documentcloud.projects.serializers import (
    CollaborationSerializer,
    ProjectMembershipSerializer,
    ProjectSerializer,
)
from documentcloud.users.models import User


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    queryset = Project.objects.none()

    def get_queryset(self):
        return Project.objects.get_viewable(self.request.user)

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

    class Filter(django_filters.FilterSet):
        user = ModelMultipleChoiceFilter(model=User, field_name="collaborators")
        document = ModelMultipleChoiceFilter(model=Document, field_name="documents")

        class Meta:
            model = Project
            fields = {
                "user": ["exact"],
                "document": ["exact"],
                "private": ["exact"],
                "slug": ["exact"],
                "title": ["exact"],
            }

    filterset_class = Filter


class ProjectMembershipViewSet(BulkModelMixin, viewsets.ModelViewSet):
    serializer_class = ProjectMembershipSerializer
    queryset = ProjectMembership.objects.none()
    lookup_field = "document_id"
    permit_list_expands = ["document"]

    def get_queryset(self):
        """Only fetch projects viewable to this user"""
        project = get_object_or_404(
            Project.objects.get_viewable(self.request.user),
            pk=self.kwargs["project_pk"],
        )
        queryset = project.projectmembership_set.get_viewable(self.request.user)
        if is_expanded(self.request, "document"):
            queryset = queryset.select_related("document")
        return queryset

    def check_edit_project(self):
        project = Project.objects.get(pk=self.kwargs["project_pk"])
        if not self.request.user.has_perm("projects.change_project", project):
            raise exceptions.PermissionDenied(
                "You do not have permission to edit this project"
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
        ).update(solr_dirty=True)
        for data in validated_datas:
            transaction.on_commit(
                lambda d=data: solr_index.delay(
                    d["document"].pk,
                    solr_document={"id": d["document"].pk, "projects": project.pk},
                    field_updates={"projects": "add"},
                )
            )

    @transaction.atomic
    def bulk_perform_destroy(self, objects):
        Document.objects.filter(pk__in=[o.document.pk for o in objects]).update(
            solr_dirty=True
        )
        super().bulk_perform_destroy(objects)

    @transaction.atomic
    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        transaction.on_commit(
            lambda: solr_index.delay(
                instance.document_id,
                solr_document={
                    "id": instance.document_id,
                    "projects": instance.project_id,
                },
                field_updates={"projects": "remove"},
            )
        )

    class Filter(django_filters.FilterSet):
        class Meta:
            model = ProjectMembership
            fields = {"document_id": ["in"]}

    filterset_class = Filter


class CollaborationViewSet(viewsets.ModelViewSet):

    serializer_class = CollaborationSerializer
    queryset = Collaboration.objects.none()
    lookup_field = "user_id"

    def get_queryset(self):
        """Only fetch projects viewable to this user"""
        project = get_object_or_404(
            Project.objects.get_viewable(self.request.user),
            pk=self.kwargs["project_pk"],
        )
        if self.request.user.has_perm("projects.change_project", project):
            return project.collaboration_set.all()
        else:
            return project.collaboration_set.none()

    def perform_create(self, serializer):
        """Specify the project"""
        project = Project.objects.get(pk=self.kwargs["project_pk"])
        if not self.request.user.has_perm("projects.change_project", project):
            raise exceptions.PermissionDenied(
                "You do not have permission to add collaborators to this project"
            )

        serializer.save(project=project, creator=self.request.user)
