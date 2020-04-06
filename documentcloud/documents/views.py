# Django
from django.conf import settings
from django.db import transaction
from django.utils.cache import patch_cache_control
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_cookie
from rest_framework import mixins, parsers, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

# Standard Library
import logging
import sys
from functools import lru_cache

# Third Party
import django_filters
import environ
import pysolr
from rest_flex_fields import FlexFieldsModelViewSet

# DocumentCloud
from documentcloud.common.environment import storage
from documentcloud.core.filters import ChoicesFilter, ModelMultipleChoiceFilter
from documentcloud.core.permissions import (
    DjangoObjectPermissionsOrAnonReadOnly,
    DocumentErrorTokenPermissions,
    DocumentTokenPermissions,
)
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.decorators import conditional_cache_control
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
from documentcloud.drf_bulk.views import BulkModelMixin
from documentcloud.organizations.models import Organization
from documentcloud.projects.models import Project
from documentcloud.users.models import User

env = environ.Env()
logger = logging.getLogger(__name__)

# We use CloudFlare's Page Rules to enable aggressive caching on the document
# retrieve view.  Since we match on documents/* it also affects all other views
# served beneath that route.  We set the 'no-cache' Cache-Control header to disable
# the caching for all views besides the ones we explicitly set


@method_decorator(conditional_cache_control(no_cache=True), name="dispatch")
class DocumentViewSet(BulkModelMixin, FlexFieldsModelViewSet):
    parser_classes = (parsers.MultiPartParser, parsers.JSONParser)
    permit_list_expands = [
        "user",
        "user.organization",
        "organization",
        "projects",
        "sections",
        "notes",
        "notes.user",
        "notes.user.organization",
        "notes.organization",
    ]
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
        if valid_token:
            queryset = Document.objects.all()
        else:
            queryset = Document.objects.get_viewable(self.request.user)

        queryset = queryset.preload(
            self.request.user, self.request.query_params.get("expand", "")
        )

        return queryset

    def filter_update_queryset(self, queryset):
        return queryset.get_editable(self.request.user)

    @vary_on_cookie
    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        has_auth_token = hasattr(request, "auth") and request.auth is not None
        if has_auth_token or request.user.is_authenticated:
            patch_cache_control(response, private=True, no_cache=True)
        else:
            patch_cache_control(
                response, public=True, max_age=settings.CACHE_CONTROL_MAX_AGE
            )
        return response

    @transaction.atomic
    def perform_create(self, serializer):

        bulk = hasattr(serializer, "many") and serializer.many

        if bulk:
            file_urls = [d.pop("file_url", None) for d in serializer.validated_data]
        else:
            file_urls = [serializer.validated_data.pop("file_url", None)]

        documents = serializer.save(
            user=self.request.user, organization=self.request.user.organization
        )

        if not bulk:
            documents = [documents]

        for document, file_url in zip(documents, file_urls):
            if file_url is not None:
                transaction.on_commit(
                    lambda d=document, f=file_url: fetch_file_url.delay(f, d.pk)
                )

    @action(detail=True, methods=["post"])
    def process(self, request, pk=None):
        """Process a document after you have uploaded the file"""
        # pylint: disable=unused-argument
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
        if len(request.data["ids"]) > settings.REST_BULK_LIMIT:
            return Response(
                {
                    "error": "Bulk API operations are limited to "
                    f"{settings.REST_BULK_LIMIT} documents at a time"
                },
                status=status.HTTP_400_BAD_REQUEST,
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
            transaction.on_commit(
                lambda: solr_index.delay(document.pk, field_updates={"status": "set"})
            )
            if was_public:
                # if document is public, mark the files as private while it is being
                # processed
                transaction.on_commit(lambda: update_access.delay(document.pk))
        process.delay(document.pk, document.slug)

    @process.mapping.delete
    def cancel_process(self, request, pk=None):
        """Cancel processing for a document"""
        # pylint: disable=unused-argument
        document = self.get_object()
        if document.status not in (Status.pending, Status.readable):
            return Response(
                {"error": "Not processing"}, status=status.HTTP_400_BAD_REQUEST
            )
        with transaction.atomic():
            document.status = Status.error
            document.save()
            transaction.on_commit(
                lambda: solr_index.delay(document.pk, field_updates={"status": "set"})
            )
            document.errors.create(message="Processing was cancelled")
            transaction.on_commit(lambda: process_cancel.delay(document.pk))
            return Response("OK", status=status.HTTP_200_OK)

    def perform_destroy(self, instance):
        if instance.status in (Status.pending, Status.readable):
            # if still processing, cancel before deleting
            process_cancel.delay(instance.pk)
        instance.destroy()

    def check_bulk_destroy_permissions(self, queryset):

        super().check_bulk_destroy_permissions(queryset)

        if "id__in" not in self.request.GET:
            raise serializers.ValidationError(
                "May not bulk delete unless you explicitly specify IDs"
            )

        if len(self.request.GET["id__in"].split(",")) != queryset.count():
            raise serializers.ValidationError("Could not find all objects to delete")

    @transaction.atomic
    def perform_update(self, serializer):
        # work for regular and bulk updates

        bulk = hasattr(serializer, "many") and serializer.many

        if bulk:
            validated_datas = sorted(serializer.validated_data, key=lambda d: d["id"])
            # get the relevant instances
            instances = serializer.instance.filter(
                id__in=[d["id"] for d in validated_datas]
            ).order_by("id")
            if len(validated_datas) != len(instances):
                raise serializers.ValidationError(
                    "Could not find all objects to update"
                )
        else:
            validated_datas = [serializer.validated_data]
            instances = [serializer.instance]

        was_publics = [i.public for i in instances]
        old_statuses = [i.status for i in instances]
        super().perform_update(serializer)

        # refresh from database after performing update
        if bulk:
            instances = sorted(serializer.instance, key=lambda i: i.id)
        else:
            instances = [serializer.instance]

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
                # never try to update the id
                validated_data.pop("id", None)
                transaction.on_commit(
                    lambda i=instance: solr_index.delay(
                        i.pk, field_updates={f: "set" for f in validated_data}
                    )
                )

    @action(detail=False, methods=["get"])
    def search(self, request):
        try:
            response = search(request.user, request.query_params)
        except pysolr.SolrError as exc:
            logger.error(
                "Solr Error: User: %s Query Params: %s Exc: %s",
                request.user,
                request.query_params,
                exc,
                exc_info=sys.exc_info(),
            )
            return Response(
                {"error": "There has been an error with your search query"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        else:
            return Response(response)

    @action(detail=True, url_path="search", methods=["get"])
    def page_search(self, request, pk=None):
        query = request.query_params.get("q", "*:*")
        try:
            results = SOLR.search(
                query, fq=f"id:{pk}", **{"hl.snippets": settings.SOLR_HL_SNIPPETS}
            )
        except pysolr.SolrError as exc:
            logger.error(
                "Solr Error (Page): User: %s Query Params: %s Exc: %s",
                request.user,
                request.query_params,
                exc,
                exc_info=sys.exc_info(),
            )
            return Response(
                {"error": "There has been an error with your search query"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        else:
            return Response(results.highlighting.get(pk, {}))

    class Filter(django_filters.FilterSet):
        ordering = django_filters.OrderingFilter(
            fields=("created_at", "page_count", "title", "source")
        )
        user = ModelMultipleChoiceFilter(model=User)
        organization = ModelMultipleChoiceFilter(model=Organization)
        project = ModelMultipleChoiceFilter(model=Project, field_name="projects")
        access = ChoicesFilter(choices=Access)
        status = ChoicesFilter(choices=Status)

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


@method_decorator(conditional_cache_control(no_cache=True), name="dispatch")
class DocumentErrorViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    serializer_class = DocumentErrorSerializer
    queryset = DocumentError.objects.none()
    permission_classes = (
        DjangoObjectPermissionsOrAnonReadOnly | DocumentErrorTokenPermissions,
    )

    @lru_cache()
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


@method_decorator(conditional_cache_control(no_cache=True), name="dispatch")
class NoteViewSet(FlexFieldsModelViewSet):
    serializer_class = NoteSerializer
    permit_list_expands = ["user", "organization"]
    queryset = Note.objects.none()

    @lru_cache()
    def get_queryset(self):
        """Only fetch both documents and notes viewable to this user"""
        document = get_object_or_404(
            Document.objects.get_viewable(self.request.user),
            pk=self.kwargs["document_pk"],
        )
        return document.notes.get_viewable(self.request.user).preload(
            self.request.user, self.request.query_params.get("expand", "")
        )

    def perform_create(self, serializer):
        """Specify the document, user and organization"""
        serializer.save(
            document_id=self.kwargs["document_pk"],
            user=self.request.user,
            organization=self.request.user.organization,
        )


@method_decorator(conditional_cache_control(no_cache=True), name="dispatch")
class SectionViewSet(viewsets.ModelViewSet):
    serializer_class = SectionSerializer
    queryset = Section.objects.none()

    @lru_cache()
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


@method_decorator(conditional_cache_control(no_cache=True), name="dispatch")
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


@method_decorator(conditional_cache_control(no_cache=True), name="dispatch")
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


@method_decorator(conditional_cache_control(no_cache=True), name="dispatch")
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

        # remove duplicate values
        document.data[pk] = list(set(serializer.data["values"]))
        document.save()
        transaction.on_commit(
            lambda: solr_index.delay(document.pk, field_updates={f"data_{pk}": "set"})
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

        # remove duplicate values
        document.data[pk] = list(set(document.data[pk]))

        if not document.data[pk]:
            # remove key if all values are removed
            del document.data[pk]

        document.save()
        transaction.on_commit(
            lambda: solr_index.delay(document.pk, field_updates={f"data_{pk}": "set"})
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
                    document.pk, field_updates={f"data_{pk}": "set"}
                )
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(conditional_cache_control(no_cache=True), name="dispatch")
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

        was_public = document.public
        with transaction.atomic():
            document.status = Status.pending
            document.save()
            transaction.on_commit(
                lambda: solr_index.delay(document.pk, field_updates={"status": "set"})
            )
            if was_public:
                # if document is public, mark the files as private while it is being
                # processed
                transaction.on_commit(lambda: update_access.delay(document.pk))

        redact.delay(document.pk, document.slug, serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
