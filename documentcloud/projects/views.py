# Django
from django.db import transaction
from rest_framework import exceptions, serializers, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import SAFE_METHODS

# Standard Library
from functools import lru_cache

# Third Party
import django_filters
from rest_flex_fields.views import FlexFieldsModelViewSet

# DocumentCloud
from documentcloud.core.filters import ModelMultipleChoiceFilter
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
    permit_list_expands = ["document"] + [
        f"document.{e}" for e in DocumentViewSet.permit_list_expands
    ]

    @lru_cache()
    def get_queryset(self):
        """Only fetch projects viewable to this user"""
        project = get_object_or_404(
            Project.objects.get_viewable(self.request.user),
            pk=self.kwargs["project_pk"],
        )
        return project.projectmembership_set.get_viewable(self.request.user).preload(
            self.request.user, self.request.query_params.get("expand", "")
        )

    @lru_cache()
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
            self._solr_add(data)

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
        ).update(solr_dirty=True)
        for data in validated_datas:
            self._solr_update(data)

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
        ).update(solr_dirty=True)
        # create new memberships and update existing memberships
        memberships = []
        for document, data in data_mapping.items():
            membership = membership_mapping.get(document)
            if membership is None:
                # add the project id into the data before creating
                data["project_id"] = self.kwargs["project_pk"]
                memberships.append(serializer.child.create(data))
                self._solr_add(data)
            else:
                memberships.append(serializer.child.update(membership, data))
                self._solr_update(data)

        # delete existing memberships not present in the data
        delete = [m for d, m in membership_mapping.items() if d not in data_mapping]
        ProjectMembership.objects.filter(pk__in=[m.pk for m in delete]).delete()
        for membership in delete:
            self._solr_remove(membership)

        return memberships

    @transaction.atomic
    def bulk_perform_destroy(self, objects):
        Document.objects.filter(pk__in=[o.document.pk for o in objects]).update(
            solr_dirty=True
        )
        ProjectMembership.objects.filter(pk__in=[o.pk for o in objects]).delete()
        for obj in objects:
            self._solr_remove(obj)

    @transaction.atomic
    def perform_destroy(self, instance):
        instance.document.solr_dirty = True
        instance.document.save()
        super().perform_destroy(instance)
        self._solr_remove(instance)

    def _solr_add(self, data):
        """Add the project to the document's solr index"""
        # if this document has edit access in the project, we store it
        # to both projects and projects_edit_access in solr
        # projects is used for displaying and querying which projects a
        # document belongs to
        # projects_edit_access is used to filter on for access permissions
        # to determine if you can view that document
        # update and destroy have similarly will add or remove from
        # the necessary fields
        project_pk = int(self.kwargs["project_pk"])
        solr_document = {"id": data["document"].pk, "projects": project_pk}
        field_updates = {"projects": "add"}
        if data.get("edit_access"):
            solr_document["projects_edit_access"] = project_pk
            field_updates["projects_edit_access"] = "add"
        transaction.on_commit(
            lambda: solr_index.delay(data["document"].pk, solr_document, field_updates)
        )

    def _solr_update(self, data):
        """Update the project on the document's solr index"""
        solr_document = {
            "id": data["document"].pk,
            "projects_edit_access": int(self.kwargs["project_pk"]),
        }
        if data.get("edit_access"):
            field_updates = {"projects_edit_access": "add"}
        else:
            field_updates = {"projects_edit_access": "remove"}
        transaction.on_commit(
            lambda: solr_index.delay(data["document"].pk, solr_document, field_updates)
        )

    def _solr_remove(self, instance):
        """Remove the project from the document's solr index"""
        solr_document = {"id": instance.document_id, "projects": instance.project_id}
        field_updates = {"projects": "remove"}
        if instance.edit_access:
            solr_document["projects_edit_access"] = instance.project_id
            field_updates["projects_edit_access"] = "remove"
        transaction.on_commit(
            lambda: solr_index.delay(instance.document_id, solr_document, field_updates)
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
