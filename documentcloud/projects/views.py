# Django
from django.db import transaction
from rest_framework import mixins, serializers, viewsets
from rest_framework.generics import get_object_or_404

# Third Party
import django_filters

# DocumentCloud
from documentcloud.core.filters import ModelMultipleChoiceFilter
from documentcloud.documents.models import Document
from documentcloud.documents.tasks import solr_index
from documentcloud.drf_bulk.views import BulkModelMixin
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
            project=project, user=self.request.user, creator=self.request.user
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

    def get_queryset(self):
        """Only fetch projects viewable to this user"""
        project = get_object_or_404(
            Project.objects.get_viewable(self.request.user),
            pk=self.kwargs["project_pk"],
        )
        return project.projectmembership_set.all()

    @transaction.atomic
    def perform_create(self, serializer):
        """Specify the project"""
        project = Project.objects.get(pk=self.kwargs["project_pk"])
        if not self.request.user.has_perm("projects.change_project", project):
            raise serializers.ValidationError(
                "You do not have permission to add documents to this project"
            )
        serializer.save(project=project)
        # XXX make this work for bulk
        transaction.on_commit(
            lambda: solr_index.delay(
                serializer.data["document"],
                solr_document={
                    "id": serializer.data["document"],
                    "projects": project.pk,
                },
                field_updates={"projects": "add"},
            )
        )

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


class CollaborationViewSet(
    # Cannot update collaborators
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):

    serializer_class = CollaborationSerializer
    queryset = Collaboration.objects.none()
    lookup_field = "user_id"

    def get_queryset(self):
        """Only fetch projects viewable to this user"""
        project = get_object_or_404(
            Project.objects.get_viewable(self.request.user),
            pk=self.kwargs["project_pk"],
        )
        return project.collaboration_set.all()

    def perform_create(self, serializer):
        """Specify the project"""
        project = Project.objects.get(pk=self.kwargs["project_pk"])
        if not self.request.user.has_perm("projects.change_project", project):
            raise serializers.ValidationError(
                "You do not have permission to add collaborators to this project"
            )

        serializer.save(project=project, creator=self.request.user)
