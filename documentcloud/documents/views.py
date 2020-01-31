# Django
from django.conf import settings
from django.db import transaction
from django.db.models.query import QuerySet
from rest_framework import mixins, parsers, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

# Third Party
import django_filters
import environ
from rest_flex_fields import FlexFieldsModelViewSet

# DocumentCloud
from documentcloud.common.environment import storage
from documentcloud.core.filters import ModelChoiceFilter
from documentcloud.core.permissions import (
    DjangoObjectPermissionsOrAnonReadOnly,
    DocumentErrorTokenPermissions,
    DocumentTokenPermissions,
)
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.models import (
    Document,
    DocumentError,
    Entity,
    EntityDate,
    Note,
    Section,
)
from documentcloud.documents.search import SOLR, search
from documentcloud.documents.serializers import (
    DataAddRemoveSerializer,
    DataSerializer,
    DocumentErrorSerializer,
    DocumentSerializer,
    EntityDateSerializer,
    EntitySerializer,
    NoteSerializer,
    RedactionSerializer,
    SectionSerializer,
)
from documentcloud.documents.tasks import (
    fetch_file_url,
    process,
    process_cancel,
    redact,
    solr_index,
    update_access,
)
from documentcloud.organizations.models import Organization
from documentcloud.projects.models import Project
from documentcloud.users.models import User

env = environ.Env()


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

    def create(self, request):
        """Handle single and bulk creations"""
        if isinstance(request.data, list):
            serializer = self.get_serializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=True)
            self.perform_bulk_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return super().create(request)

    def perform_bulk_create(self, serializer):
        return self.perform_create(serializer, bulk=True)

    @transaction.atomic
    def perform_create(self, serializer, bulk=False):

        # only support file_url for non-bulk creations
        if not bulk:
            file_url = serializer.validated_data.pop("file_url", None)

        document = serializer.save(
            user=self.request.user, organization=self.request.user.organization
        )

        if not bulk and file_url is not None:
            transaction.on_commit(lambda: fetch_file_url.delay(file_url, document.pk))

    @action(detail=True, methods=["post"])
    def process(self, request, pk=None):
        """Process a document after you have uploaded the file"""
        # pylint: disable=unused-argument
        # XXX do we limit this to documents you can edit?
        document = self.get_object()
        error = self._check_process(document)
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)
        else:
            self._process(document)
            return Response("OK", status=status.HTTP_200_OK)

    @action(detail=False, url_path="process", methods=["post"])
    def bulk_process(self, request):
        """Bulk process documents"""
        if "ids" not in request.data:
            return Response(
                {"error": "`ids` not specified"}, status=status.HTTP_400_BAD_REQUEST
            )
        documents = Document.objects.filter(pk__in=request.data["ids"])

        errors = []
        for document in documents:
            error = self._check_process(document)
            if error:
                errors.append(error)
        if errors:
            return Response({"error": errors}, status=status.HTTP_400_BAD_REQUEST)

        for document in documents:
            self._process(document)
        return Response("OK", status=status.HTTP_200_OK)

    def _check_process(self, document):
        """Check the document is in a suitable state for processing"""

        if not self.request.user.has_perm("documents.change_document", document):
            return f"You do not have permission to edit document {document.pk}"

        if not storage.exists(document.doc_path):
            return f"No File: {document.pk}"

        if document.status in (Status.pending, Status.readable):
            return f"Already processing: {document.pk}"

        return None

    def _process(self, document):
        """Process a document after you have uploaded the file"""
        was_public = document.public
        with transaction.atomic():
            document.status = Status.pending
            document.save()
            if was_public:
                # if document is public, mark the files as private while it is being
                # processed
                transaction.on_commit(lambda: update_access.delay(document.pk))
        process.delay(document.pk, document.slug)

    @process.mapping.delete
    def cancel_process(self, request, pk=None):
        """Cancel processing for a document"""
        document = self.get_object()
        if document.status not in (Status.pending, Status.readable):
            return Response(
                {"error": "Not processing"}, status=status.HTTP_400_BAD_REQUEST
            )
        with transaction.atomic():
            document.status = Status.error
            document.save()
            document.errors.create(message="Processing was cancelled")
            transaction.on_commit(lambda: process_cancel.delay(document.pk))
            return Response("OK", status=status.HTTP_200_OK)

    def perform_destroy(self, instance):
        instance.destroy()

    @transaction.atomic
    def perform_update(self, serializer):
        # work for regular and bulk updates
        if isinstance(serializer.instance, QuerySet):
            instances = serializer.instance
            validated_datas = serializer.validated_data
        else:
            instances = [serializer.instance]
            validated_datas = [serializer.validated_data]

        was_publics = [i.public for i in instances]
        old_statuses = [i.status for i in instances]
        super().perform_update(serializer)
        for instance, validated_data, was_public, old_status in zip(
            instances, validated_datas, was_publics, old_statuses
        ):
            if was_public != instance.public:
                transaction.on_commit(lambda i=instance: update_access.delay(i.pk))
            if old_status in (Status.pending, Status.readable):
                # if we were processing, do a full update
                if instance.status == Status.success:
                    # if it was processed succesfully, index the text
                    transaction.on_commit(
                        lambda i=instance: solr_index.delay(i.pk, index_text=True)
                    )
                else:
                    # if it is not done processing or error, just update other fields
                    transaction.on_commit(lambda i=instance: solr_index.delay(i.pk))
            else:
                # only update the fields that were updated
                fields = validated_data.keys()
                transaction.on_commit(
                    lambda i=instance: solr_index.delay(
                        i.pk, field_updates={f: "set" for f in fields}
                    )
                )

    def bulk_partial_update(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        if len(request.data) != len(queryset):
            return Response(
                {"error": "Bad document ID"}, status=status.HTTP_400_BAD_REQUEST
            )
        errors = []
        for document in queryset:
            if not request.user.has_perm("documents.change_document", document):
                errors.append(f"Do not have permission to edit {document.pk}")
        if errors:
            return Response({"error": errors}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(
            queryset, data=request.data, many=True, partial=True
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def bulk_destroy(self, request):
        if "id__in" not in request.GET:
            return Response(
                {"error": "May not bulk delete unless you explicitly specify IDs"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = self.filter_queryset(self.get_queryset())

        errors = []
        for document in queryset:
            if not request.user.has_perm("documents.delete_document", document):
                errors.append(f"Do not have permission to delete {document.pk}")
        if errors:
            return Response({"error": errors}, status=status.HTTP_403_FORBIDDEN)

        for document in queryset:
            self.perform_destroy(document)

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def search(self, request):
        return Response(search(self.request.user, self.request.query_params))

    @action(detail=True, url_path="search", methods=["get"])
    def page_search(self, request, pk=None):
        query = request.query_params.get("q", "*:*")
        results = SOLR.search(query, fq=f"id:{pk}")
        pages = [int(p.rsplit("_", 1)[1]) for p in results.highlighting.get(pk, {})]
        return Response({"results": pages})

    class Filter(django_filters.FilterSet):
        ordering = django_filters.OrderingFilter(
            fields=("created_at", "page_count", "title", "source")
        )
        user = ModelChoiceFilter(model=User)
        organization = ModelChoiceFilter(model=Organization)
        project = ModelChoiceFilter(model=Project, field_name="projects")
        access = django_filters.CharFilter(method="filter_access")
        status = django_filters.CharFilter(method="filter_status")

        def filter_access(self, queryset, name, value):
            return self.filter_choices(Access, queryset, name, value)

        def filter_status(self, queryset, name, value):
            return self.filter_choices(Status, queryset, name, value)

        def filter_choices(self, choices, queryset, name, value):
            value_map = {
                label.lower(): choice.value for label, choice in choices._fields.items()
            }
            return queryset.filter(**{name: value_map.get(value.lower())})

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
                "id": ["in"],
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
        valid_token = (
            hasattr(self.request, "auth")
            and self.request.auth is not None
            and "processing" in self.request.auth["permissions"]
        )
        # Processing scope can access all documents
        if valid_token:
            documents = Document.objects.all()
        else:
            documents = Document.objects.get_viewable(self.request.user)
        self.document = get_object_or_404(documents, pk=self.kwargs["document_pk"])
        return self.document.errors.all()

    @transaction.atomic
    def perform_create(self, serializer):
        """Specify the document
        Set the status of the document to error
        """
        serializer.save(document_id=self.document.pk)
        self.document.status = Status.error
        self.document.save()
        transaction.on_commit(
            lambda: solr_index.delay(self.document.pk, field_updates={"status": "set"})
        )


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


class DataViewSet(viewsets.ViewSet):
    # pylint: disable=unused-argument
    serializer_class = DataSerializer
    permission_classes = (IsAuthenticatedOrReadOnly,)

    def get_object(self, edit=False):
        document = get_object_or_404(
            Document.objects.get_viewable(self.request.user),
            pk=self.kwargs["document_pk"],
        )
        if edit and not self.request.user.has_perm(
            "documents.change_document", document
        ):
            self.permission_denied(self.request, "You may not edit this document")
        return document

    def list(self, request, document_pk=None):
        document = self.get_object()
        return Response(document.data)

    def retrieve(self, request, pk=None, document_pk=None):
        document = self.get_object()
        return Response(document.data.get(pk))

    @transaction.atomic
    def update(self, request, pk=None, document_pk=None):
        document = self.get_object(edit=True)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        document.data[pk] = serializer.data["values"]
        document.save()
        transaction.on_commit(
            lambda: solr_index.delay(
                self.document.pk, field_updates={f"data_{pk}": "set"}
            )
        )
        return Response(document.data)

    @transaction.atomic
    def partial_update(self, request, pk=None, document_pk=None):
        document = self.get_object(edit=True)
        serializer = DataAddRemoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if pk in document.data:
            document.data[pk].extend(serializer.data.get("values", []))
            document.data[pk] = [
                i
                for i in document.data[pk]
                if i not in serializer.data.get("remove", [])
            ]
        else:
            document.data[pk] = serializer.data.get("values", [])

        if not document.data[pk]:
            # remove key if all values are removed
            del document.data[pk]

        document.save()
        transaction.on_commit(
            lambda: solr_index.delay(
                self.document.pk, field_updates={f"data_{pk}": "set"}
            )
        )
        return Response(document.data)

    @transaction.atomic
    def destroy(self, request, pk=None, document_pk=None):
        document = self.get_object(edit=True)

        if pk in document.data:
            del document.data[pk]
            document.save()
            transaction.on_commit(
                lambda: solr_index.delay(
                    self.document.pk, field_updates={f"data_{pk}": "set"}
                )
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class RedactionViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = RedactionSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        document = get_object_or_404(
            Document.objects.get_viewable(self.request.user),
            pk=self.kwargs["document_pk"],
        )
        if not self.request.user.has_perm("documents.change_document", document):
            self.permission_denied(self.request, "You may not edit this document")
        return document

    def create(self, request, *args, **kwargs):
        document = self.get_object()
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        if document.status in (Status.pending, Status.readable):
            return Response(
                {"error": "Already processing"}, status=status.HTTP_400_BAD_REQUEST
            )

        # TODO: maybe refactor general processing checks as a mixin
        was_public = document.public
        with transaction.atomic():
            document.status = Status.pending
            document.save()
            if was_public:
                # if document is public, mark the files as private while it is being
                # processed
                transaction.on_commit(lambda: update_access.delay(document.pk))

        redact.delay(document.pk, document.slug, serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
