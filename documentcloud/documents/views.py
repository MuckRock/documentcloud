# Django
from django import forms
from django.conf import settings
from django.db import transaction
from rest_framework import parsers, viewsets

# Standard Library
import os

# Third Party
import django_filters
import environ

# DocumentCloud
from documentcloud.core.filters import ModelChoiceFilter
from documentcloud.documents.models import Document
from documentcloud.documents.serializers import DocumentSerializer
from documentcloud.organizations.models import Organization
from documentcloud.users.models import User

env = environ.Env()


class DocumentViewSet(viewsets.ModelViewSet):
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
            # XXX what path do we save files to
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
        transaction.on_commit(
            lambda: httpsub.post(settings.DOC_PROCESSING_URL, json=options)
        )

    class Filter(django_filters.FilterSet):
        ordering = django_filters.OrderingFilter(
            fields=("created_at", "page_count", "title", "source")
        )
        user = ModelChoiceFilter(model=User)
        organization = ModelChoiceFilter(model=Organization)

        class Meta:
            model = Document
            fields = {
                "user": ["exact"],
                "organization": ["exact"],
                "access": ["exact"],
                "status": ["exact"],
                "created_at": ["lt", "gt"],
                "page_count": ["exact", "lt", "gt"],
            }

    filterset_class = Filter
