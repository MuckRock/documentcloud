# Django
from django.conf import settings
from django.db import transaction
from rest_framework import parsers, viewsets

# Standard Library
import os

# Third Party
import environ

# DocumentCloud
from documentcloud.core.permissions import Permissions
from documentcloud.documents.models import Document
from documentcloud.documents.serializers import DocumentSerializer

env = environ.Env()


class DocumentViewSet(viewsets.ModelViewSet):
    parser_classes = (parsers.MultiPartParser, parsers.JSONParser)
    serializer_class = DocumentSerializer
    permissions = (Permissions,)
    queryset = Document.objects.none()

    def get_queryset(self):
        return Document.objects.select_related("user", "organization")

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
            lambda: httpsub.post(env("DOC_PROCESSING_URL"), json=options)
        )
