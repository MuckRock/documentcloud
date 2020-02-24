# Django
from django.db import transaction
from rest_framework import exceptions, serializers, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import SAFE_METHODS

# Third Party
import django_filters
from rest_flex_fields.utils import is_expanded
from rest_flex_fields.views import FlexFieldsModelViewSet

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


class ProjectMembershipViewSet(BulkModelMixin, FlexFieldsModelViewSet):
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
            # if this document has edit access in the project, we store it
            # to both projects and projects_edit_access in solr
            # projects is used for displaying and querying which projects a
            # document belongs to
            # projects_edit_access is used to filter on for access permissions
            # to determine if you can view that document
            # update and destroy have similarly will add or remove from
            # the necessary fields
            solr_document = {"id": data["document"].pk, "projects": project.pk}
            field_updates = {"projects": "add"}
            if data.get("edit_access"):
                solr_document["projects_edit_access"] = project.pk
                field_updates["projects_edit_access"] = "add"
            transaction.on_commit(
                lambda d=data, sd=solr_document, fu=field_updates: solr_index.delay(
                    d["document"].pk, solr_document=sd, field_updates=fu
                )
            )

    @transaction.atomic
    def perform_update(self, serializer):
        super().perform_update(serializer)

        project_id = self.kwargs["project_pk"]
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
        ).update(solr_dirty=True)
        for data in validated_datas:
            transaction.on_commit(
                lambda d=data: solr_index.delay(
                    d["document"].pk,
                    solr_document={
                        "id": d["document"].pk,
                        "projects_edit_access": project_id,
                    },
                    field_updates={
                        "projects_edit_access": "add"
                        if d.get("edit_access")
                        else "remove"
                    },
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
        instance.document.solr_dirty = True
        instance.document.save()
        super().perform_destroy(instance)
        solr_document = {"id": instance.document_id, "projects": instance.project_id}
        field_updates = {"projects": "remove"}
        if instance.edit_access:
            solr_document["projects_edit_access"] = instance.project_id
            field_updates["projects_edit_access"] = "remove"
        transaction.on_commit(
            lambda: solr_index.delay(
                instance.document_id,
                solr_document=solr_document,
                field_updates=field_updates,
            )
        )

    class Filter(django_filters.FilterSet):
        class Meta:
            model = ProjectMembership
            fields = {"document_id": ["in"]}

    filterset_class = Filter


class CollaborationViewSet(FlexFieldsModelViewSet):

    serializer_class = CollaborationSerializer
    queryset = Collaboration.objects.none()
    lookup_field = "user_id"
    permit_list_expands = ["user"]

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

        if is_expanded(self.request, "user"):
            queryset = queryset.select_related("user")

        return queryset

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
