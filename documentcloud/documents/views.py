# Django
from django import forms
from django.conf import settings
from django.db import transaction
from rest_framework import mixins, parsers, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

# Standard Library
import os
import uuid

# Third Party
import django_filters
import environ
from rest_flex_fields import FlexFieldsModelViewSet

# DocumentCloud
from documentcloud.core.filters import ModelChoiceFilter
from documentcloud.core.permissions import (
    DjangoObjectPermissionsOrAnonReadOnly,
    DocumentErrorTokenPermissions,
    DocumentTokenPermissions,
)
from documentcloud.documents.models import (
    Document,
    DocumentError,
    Entity,
    EntityDate,
    Note,
    Section,
)
from documentcloud.documents.serializers import (
    DocumentErrorSerializer,
    DocumentSerializer,
    EntityDateSerializer,
    EntitySerializer,
    NoteSerializer,
    SectionSerializer,
)
from documentcloud.documents.tasks import fetch_file_url
from documentcloud.environment.environment import httpsub, storage
from documentcloud.organizations.models import Organization
from documentcloud.projects.models import Project
from documentcloud.users.models import User

env = environ.Env()


class SignedPutURIView(APIView):
    """
    Generate a signed url for the user to upload a file to S3.
    """

    # XXX put this into the doc viewset

    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):

        key = "{}/{}".format(request.user.username, uuid.uuid4())
        upload_uri = storage.presign_url(key)
        data = {"key": key, "upload_uri": upload_uri}
        return Response(data=data, status=status.HTTP_200_OK)


class DocumentViewSet(FlexFieldsModelViewSet):
    parser_classes = (parsers.MultiPartParser, parsers.JSONParser)
    permit_list_expands = ["user", "organization"]
    serializer_class = DocumentSerializer
    queryset = Document.objects.none()
    permission_classes = (
        DjangoObjectPermissionsOrAnonReadOnly | DocumentTokenPermissions,
    )

    def get_queryset(self):
        valid_token = (
            hasattr(self.request, "auth")
            and self.request.auth is not None
            and "processing" in self.request.auth["permissions"]
        )
        # Processing scope can access all documents
        queryset = Document.objects.select_related("user", "organization")
        if not valid_token:
            queryset = queryset.get_viewable(self.request.user)
        return queryset

    @action(detail=False, methods=["post"])
    def signed_uri(self, request):
        """Generate a signed url for the user to upload a file to S3"""

        key_uuid = uuid.uuid4()
        upload_uri = storage.presign_url(f"{request.user.pk}/{key_uuid}")
        data = {"key": key_uuid, "upload_uri": upload_uri}
        return Response(data=data, status=status.HTTP_200_OK)

    @transaction.atomic
    def perform_create(self, serializer):

        key = serializer.validated_data.pop("key", None)
        file_url = serializer.validated_data.pop("file_url", None)

        document = serializer.save(
            user=self.request.user, organization=self.request.user.organization
        )

        options = {"document": document.pk}

        if key is not None:
            dst_key = f"{document.id}/{document.slug}.pdf"
            storage.copy(
                settings.UPLOAD_BUCKET,
                f"{self.request.user.pk}/{key}",
                settings.DOCUMENT_BUCKET,
                dst_key,
            )
            options["path"] = dst_key
            transaction.on_commit(
                lambda: httpsub.post(settings.DOC_PROCESSING_URL, json=options)
            )
        else:
            transaction.on_commit(
                lambda: fetch_file_url.delay(file_url, document.pk, document.slug)
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


class DocumentErrorViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    serializer_class = DocumentErrorSerializer
    queryset = DocumentError.objects.none()
    permission_classes = (
        DjangoObjectPermissionsOrAnonReadOnly | DocumentErrorTokenPermissions,
    )

    def get_queryset(self):
        """Only fetch documents viewable to this user"""
        document = get_object_or_404(
            Document.objects.get_viewable(self.request.user),
            pk=self.kwargs["document_pk"],
        )
        return document.errors.all()

    def perform_create(self, serializer):
        """Specify the document"""
        serializer.save(document_id=self.kwargs["document_pk"])


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
