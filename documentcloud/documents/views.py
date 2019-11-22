# Django
from django.db import transaction
from rest_framework import mixins, parsers, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

# Third Party
import django_filters
import environ
import pysolr
from rest_flex_fields import FlexFieldsModelViewSet

# DocumentCloud
from documentcloud.common.environment import storage
from documentcloud.core.filters import ModelChoiceFilter
from documentcloud.core.permissions import (
    DjangoObjectPermissionsOrAnonReadOnly,
    DocumentErrorTokenPermissions,
    DocumentTokenPermissions,
)
from documentcloud.documents.choices import Status
from documentcloud.documents.models import (
    Document,
    DocumentError,
    Entity,
    EntityDate,
    Note,
    Section,
)
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
    create_redaction,
    delete_document,
    fetch_file_url,
    process,
    process_cancel,
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

    @transaction.atomic
    def perform_create(self, serializer):

        file_url = serializer.validated_data.pop("file_url", None)

        document = serializer.save(
            user=self.request.user, organization=self.request.user.organization
        )

        if file_url is not None:
            transaction.on_commit(lambda: fetch_file_url.delay(file_url, document.pk))

    @action(detail=True, methods=["post"])
    def process(self, request, pk=None):
        """Process a document after you have uploaded the file"""
        # pylint: disable=unused-argument
        document = self.get_object()
        if not storage.exists(document.doc_path):
            return Response({"error": "No file"}, status=status.HTTP_400_BAD_REQUEST)

        if document.status in (Status.pending, Status.readable):
            return Response(
                {"error": "Already processing"}, status=status.HTTP_400_BAD_REQUEST
            )

        was_public = document.public
        with transaction.atomic():
            document.status = Status.pending
            document.save()
            if was_public:
                # if document is public, mark the files as private while it is being
                # processed
                transaction.on_commit(lambda: update_access.delay(document.pk))
        process.delay(document.pk, document.slug)
        return Response(status=status.HTTP_200_OK)

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

    def perform_destroy(self, instance):
        delete_document.delay(instance.pk, instance.path)
        super().perform_destroy(instance)

    @transaction.atomic
    def perform_update(self, serializer):
        was_public = serializer.instance.public
        super().perform_update(serializer)
        if was_public != serializer.instance.public:
            transaction.on_commit(lambda: update_access.delay(serializer.instance.pk))
        # XXX handle partial updates more optimially
        if serializer.data["status"] == "success":
            transaction.on_commit(lambda: solr_index.delay(serializer.data["id"]))

    @action(detail=False, methods=["get"])
    def search(self, request):
        # XXX filter based on params
        # XXX filter based on access
        # XXX paginate
        query = request.query_params.get("q", "*:*")
        fq_map = {
            "user": "user",
            "organization": "organization",
            "access": "access",
            "status": "status",
            "project": "projects",
            "document": "id",
        }
        field_queries = []

        # XXX support multiple values
        for param, solr in fq_map.items():
            if param in request.query_params:
                value = request.query_params[param]
                field_queries.append(f"{solr}:{value}")

        solr = pysolr.Solr(
            settings.SOLR_URL, auth=settings.SOLR_AUTH, search_handler="/mainsearch"
        )
        results = solr.search(query, fq=field_queries)
        response = {
            "count": results.hits,
            "next": None,
            "previous": None,
            "results": results,
        }
        if settings.DEBUG:
            response["query"] = query
            response["fq"] = field_queries
        return Response(response)

    @action(detail=True, url_path="search", methods=["get"])
    def page_search(self, request, pk=None):
        query = request.query_params.get("q", "*:*")
        solr = pysolr.Solr(
            settings.SOLR_URL, auth=settings.SOLR_AUTH, search_handler="/mainsearch"
        )
        results = solr.search(query, fq=f"id:{pk}")
        pages = [int(p.rsplit("_", 1)[1]) for p in results.highlighting.get(pk, {})]
        return Response({"results": pages})

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

    def update(self, request, pk=None, document_pk=None):
        document = self.get_object(edit=True)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        document.data[pk] = serializer.data["values"]
        document.save()
        return Response(document.data)

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
        return Response(document.data)

    def destroy(self, request, pk=None, document_pk=None):
        document = self.get_object(edit=True)

        if pk in document.data:
            del document.data[pk]
            document.save()

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
        create_redaction.delay(document.pk, document.slug, serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
