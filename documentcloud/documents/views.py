# Django
from django import forms
from django.conf import settings
from django.db import transaction
from rest_framework import mixins, parsers, viewsets
from rest_framework.generics import get_object_or_404

# Standard Library
import os

# Third Party
import django_filters
import environ
from rest_flex_fields import FlexFieldsModelViewSet

# DocumentCloud
from documentcloud.core.filters import ModelChoiceFilter
from documentcloud.documents.models import Document, Entity, EntityDate, Note, Section
from documentcloud.documents.serializers import (
    DocumentSerializer,
    EntityDateSerializer,
    EntitySerializer,
    NoteSerializer,
    SectionSerializer,
)
from documentcloud.environment.environment import storage
from documentcloud.environment.httpsub import httpsub
from documentcloud.organizations.models import Organization
from documentcloud.projects.models import Project
from documentcloud.users.models import User

env = environ.Env()


class DocumentViewSet(FlexFieldsModelViewSet):
    parser_classes = (parsers.MultiPartParser, parsers.JSONParser)
    serializer_class = DocumentSerializer
    queryset = Document.objects.none()

    def get_queryset(self):
        return Document.objects.get_viewable(self.request.user).select_related(
            "user", "organization"
        )

    @transaction.atomic
    def perform_create(self, serializer):

        file_ = serializer.validated_data.pop("file", None)
        file_url = serializer.validated_data.pop("file_url", None)

        document = serializer.save(
            user=self.request.user, organization=self.request.user.organization
        )

        options = {"document": document.pk}

        if file_ is not None:
            path = f"documents/{document.id}/{document.slug}.pdf"
            full_path = os.path.join(settings.BUCKET, path)
            # XXX storage
            with storage.open(full_path, "wb") as dest:
                for chunk in file_.chunks():
                    dest.write(chunk)
            options["path"] = path
        else:
            # XXX where do we do the download?
            # Celery or cloud function?
            options["url"] = file_url

        # XXX httpsub
        # XXX this should be a config setting instead of direct env access
        transaction.on_commit(
            lambda: httpsub.post(settings.DOC_PROCESSING_URL, json=options)
        )

    class Filter(django_filters.FilterSet):
        ordering = django_filters.OrderingFilter(
            fields=("created_at", "page_count", "title", "source")
        )
        user = ModelChoiceFilter(model=User)
        organization = ModelChoiceFilter(model=Organization)
        project = ModelChoiceFilter(model=Project, field_name="projects")

        class Meta:
            model = Document
            fields = {
                "user": ["exact"],
                "organization": ["exact"],
                "project": ["exact"],
                "access": ["exact"],
                "status": ["exact"],
                "created_at": ["lt", "gt"],
                "page_count": ["exact", "lt", "gt"],
            }

    filterset_class = Filter


class NoteViewSet(viewsets.ModelViewSet):
    serializer_class = NoteSerializer
    queryset = Note.objects.none()

    def get_queryset(self):
        """Only fetch both documents and notes viewable to this user"""
        document = get_object_or_404(
            Document.objects.get_viewable(self.request.user),
            pk=self.kwargs["document_pk"],
        )
        return document.notes.get_viewable(self.request.user)

    def perform_create(self, serializer):
        """Specify the document, user and organization"""
        serializer.save(
            document_id=self.kwargs["document_pk"],
            user=self.request.user,
            organization=self.request.user.organization,
        )


class SectionViewSet(viewsets.ModelViewSet):
    serializer_class = SectionSerializer
    queryset = Section.objects.none()

    def get_queryset(self):
        """Only fetch documents viewable to this user"""
        document = get_object_or_404(
            Document.objects.get_viewable(self.request.user),
            pk=self.kwargs["document_pk"],
        )
        return document.sections.all()

    def perform_create(self, serializer):
        """Specify the document"""
        serializer.save(document_id=self.kwargs["document_pk"])


class EntityViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = EntitySerializer
    queryset = Entity.objects.none()

    def get_queryset(self):
        """Only fetch documents viewable to this user"""
        document = get_object_or_404(
            Document.objects.get_viewable(self.request.user),
            pk=self.kwargs["document_pk"],
        )
        return document.entities.all()


class EntityDateViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = EntityDateSerializer
    queryset = EntityDate.objects.none()

    def get_queryset(self):
        """Only fetch documents viewable to this user"""
        document = get_object_or_404(
            Document.objects.get_viewable(self.request.user),
            pk=self.kwargs["document_pk"],
        )
        return document.dates.all()
