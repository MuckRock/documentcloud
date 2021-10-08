# Django
from django.conf import settings
from django.db import transaction
from django.db.models import Q, prefetch_related_objects
from django.db.models.query import Prefetch
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions, mixins, parsers, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

# Standard Library
import logging
import sys
from functools import lru_cache

# Third Party
import environ
import pysolr
from django_filters import rest_framework as django_filters
from requests.exceptions import RequestException
from rest_flex_fields import FlexFieldsModelViewSet
from rest_flex_fields.utils import split_levels

# DocumentCloud
from documentcloud.common.environment import httpsub
from documentcloud.core.choices import Language
from documentcloud.core.filters import ChoicesFilter, ModelMultipleChoiceFilter
from documentcloud.core.permissions import (
    DjangoObjectPermissionsOrAnonReadOnly,
    DocumentErrorTokenPermissions,
    DocumentPostProcessPermissions,
    DocumentTokenPermissions,
)
from documentcloud.documents.choices import Access, EntityKind, OccurrenceKind, Status
from documentcloud.documents.constants import DATA_KEY_REGEX
from documentcloud.documents.decorators import (
    anonymous_cache_control,
    conditional_cache_control,
)
from documentcloud.documents.models import (
    Document,
    DocumentError,
    EntityDate,
    EntityOccurrence,
    LegacyEntity,
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
    EntityOccurrenceSerializer,
    LegacyEntitySerializer,
    ModificationSpecSerializer,
    NoteSerializer,
    ProcessDocumentSerializer,
    RedactionSerializer,
    SectionSerializer,
)
from documentcloud.documents.tasks import (
    extract_entities,
    fetch_file_url,
    invalidate_cache,
    modify,
    post_process,
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
@method_decorator(anonymous_cache_control, name="retrieve")
class DocumentViewSet(BulkModelMixin, FlexFieldsModelViewSet):
    parser_classes = (parsers.MultiPartParser, parsers.JSONParser)
    permit_list_expands = [
        "user",
        "user.organization",
        "organization",
        "projects",
        "sections",
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

    def get_object(self):
        """Prefetch notes here if needed"""
        document = super().get_object()
        top_expands, nested_expands = split_levels(
            self.request.query_params.get("expand", "")
        )
        all_expanded = "~all" in top_expands
        nested_default = "~all" if all_expanded else ""
        if "notes" in top_expands or all_expanded:
            prefetch_related_objects(
                [document],
                Prefetch(
                    "notes",
                    Note.objects.get_viewable(self.request.user, document).preload(
                        self.request.user, nested_expands.get("notes", nested_default)
                    ),
                ),
            )
        return document

    def filter_update_queryset(self, queryset):
        return queryset.get_editable(self.request.user)

    @transaction.atomic
    def perform_create(self, serializer):

        bulk = hasattr(serializer, "many") and serializer.many

        if bulk:
            file_urls = [d.pop("file_url", None) for d in serializer.validated_data]
            force_ocrs = [d.pop("force_ocr", False) for d in serializer.validated_data]
        else:
            file_urls = [serializer.validated_data.pop("file_url", None)]
            force_ocrs = [serializer.validated_data.pop("force_ocr", False)]

        documents = serializer.save(
            user=self.request.user, organization=self.request.user.organization
        )

        if not bulk:
            documents = [documents]

        for document, file_url, force_ocr in zip(documents, file_urls, force_ocrs):
            transaction.on_commit(lambda d=document: solr_index.delay(d.pk))
            if file_url is not None:
                transaction.on_commit(
                    lambda d=document, fu=file_url, fo=force_ocr: fetch_file_url.delay(
                        fu, d.pk, fo
                    )
                )

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def process(self, request, pk=None):
        """Process a document after you have uploaded the file"""
        # pylint: disable=unused-argument
        document = self.get_object()
        document = Document.objects.select_for_update().get(pk=document.pk)
        error = self._check_process(document)
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)
        else:
            serializer = ProcessDocumentSerializer(document, data=request.data)
            serializer.is_valid(raise_exception=True)
            document.status = Status.pending
            document.save()
            self._process(document, serializer.validated_data["force_ocr"])
            return Response("OK", status=status.HTTP_200_OK)

    @transaction.atomic
    @action(detail=False, url_path="process", methods=["post"])
    def bulk_process(self, request):
        """Bulk process documents"""
        if "ids" in request.data:
            data = [{"id": i} for i in request.data["ids"]]
        else:
            data = request.data
        serializer = ProcessDocumentSerializer(
            self.filter_queryset(self.get_queryset()), data=data, many=True, bulk=True
        )
        serializer.is_valid(raise_exception=True)

        documents = Document.objects.filter(
            pk__in=[d["id"] for d in serializer.validated_data]
        ).get_editable(request.user)
        # cannot combine distinct (from get editable) with select_for_update
        documents = Document.objects.filter(
            pk__in=[d.pk for d in documents],
            status__in=(Status.success, Status.error, Status.nofile),
        ).select_for_update()
        if len(documents) != len(serializer.validated_data):
            raise serializers.ValidationError(
                "Could not find all documents to process."
            )
        force_ocr = {
            d["id"]: d.get("force_ocr", False) for d in serializer.validated_data
        }

        for document in documents:
            self._process(document, force_ocr[document.pk])
        documents.update(status=Status.pending)
        return Response("OK", status=status.HTTP_200_OK)

    def _check_process(self, document):
        """Check the document is in a suitable state for processing"""

        if not self.request.user.has_perm("documents.change_document", document):
            return f"You do not have permission to edit document {document.pk}"

        if document.processing:
            return f"Already processing: {document.pk}"

        return None

    def _process(self, document, force_ocr):
        """Process a document after you have uploaded the file"""
        transaction.on_commit(
            lambda: process.delay(
                document.pk,
                document.slug,
                document.access,
                Language.get_choice(document.language).ocr_code,
                force_ocr,
                document.original_extension,
            )
        )
        transaction.on_commit(
            lambda: solr_index.delay(document.pk, field_updates={"status": "set"})
        )

    @process.mapping.delete
    def cancel_process(self, request, pk=None):
        """Cancel processing for a document"""
        # pylint: disable=unused-argument
        document = self.get_object()
        if not document.processing:
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
        if instance.processing:
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

    def _update_validate_access(self, instances, validated_datas):
        """Validate access after instances have been filtered"""
        for instance, validated_data in zip(instances, validated_datas):
            # disallow any access change while processing
            if "access" in validated_data and instance.processing:
                raise serializers.ValidationError(
                    _("You may not update `access` while the document is processing")
                )

    @transaction.atomic
    def perform_update(self, serializer):
        # work for regular and bulk updates

        bulk = getattr(serializer, "many", False)

        if bulk:
            validated_datas = sorted(
                serializer.validated_data, key=lambda d: d.get("id", 0)
            )
            # get the relevant instances
            instances = serializer.instance.filter(
                id__in=[d.get("id", 0) for d in validated_datas]
            ).order_by("id")
        else:
            validated_datas = [serializer.validated_data]
            instances = [serializer.instance]

        self._update_validate_access(instances, validated_datas)

        old_accesses = [i.access for i in instances]
        old_processings = [i.processing for i in instances]
        old_data_keys = [i.data.keys() for i in instances]
        super().perform_update(serializer)

        # refresh from database after performing update
        if bulk:
            instances = sorted(serializer.instance, key=lambda i: i.id)
        else:
            instances = [serializer.instance]

        for instance, validated_data, old_access, old_processing, old_data_key in zip(
            instances, validated_datas, old_accesses, old_processings, old_data_keys
        ):

            self._update_access(instance, old_access, validated_data)
            self._update_solr(instance, old_processing, old_data_key, validated_data)
            self._update_cache(instance, old_processing)

    def _update_access(self, document, old_access, validated_data):
        """Update the access of a document after it has been updated"""
        # do update_access if access changed to or from public
        if old_access != document.access and Access.public in (
            old_access,
            document.access,
        ):
            status_ = document.status
            document.status = Status.readable
            # set this so that it will be updated in solr below
            validated_data["status"] = Status.readable
            # if we are making public, do not switch until the access
            # has been updated
            access = document.access
            if document.access == Access.public:
                document.access = old_access
            document.save()
            transaction.on_commit(
                lambda: update_access.delay(document.pk, status_, access)
            )

    def _update_solr(self, document, old_processing, old_data_keys, validated_data):
        """Update solr index after updating a document"""
        # update solr index
        if old_processing and document.status == Status.success:
            # if it was processed succesfully, do a full index with text
            kwargs = {"index_text": True}
        elif old_processing:
            # if it is not done processing or error, we may not be indexed yet
            # do a full index, without text since text has not been processed yet
            kwargs = {"index_text": False}
        else:
            # only update the fields that were updated
            # never try to update the id
            validated_data.pop("id", None)
            data = validated_data.pop("data", None)
            if data:
                # we want to update all data keys if data is set directly,
                # including old data keys which may have been removed
                all_keys = old_data_keys | data.keys()
                for key in all_keys:
                    validated_data[f"data_{key}"] = None
            kwargs = {"field_updates": {f: "set" for f in validated_data}}

        transaction.on_commit(lambda: solr_index.delay(document.pk, **kwargs))

    def _update_cache(self, document, old_processing):
        """Invalidate the cache when finished processing a detructive operation"""
        if old_processing and not document.processing and document.cache_dirty:
            transaction.on_commit(lambda: invalidate_cache.delay(document.pk))

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
            if "timed out" in exc.args[0]:
                code = "time out"
            else:
                code = "other"
            return Response(
                {
                    "error": "There has been an error with your search query",
                    "code": code,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        else:
            return Response(response)

    @action(detail=True, url_path="search", methods=["get"])
    def page_search(self, request, pk=None):
        query = request.query_params.get("q", "*:*")
        try:
            results = SOLR.search(
                query,
                fq=f"id:{pk}",
                **{"hl.snippets": settings.SOLR_HL_SNIPPETS, "hl.fl": "page_no_*"},
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

    @action(detail=False, methods=["get"])
    def pending(self, request):
        """Get the progress status on all of the current users pending documents"""
        if not self.request.user or not self.request.user.is_authenticated:
            return Response([])

        pending_documents = list(
            Document.objects.filter(
                user=self.request.user, status=Status.pending
            ).values_list("id", flat=True)
        )
        try:
            response = httpsub.post(
                settings.PROGRESS_URL,
                json={"doc_ids": pending_documents},
                timeout=settings.PROGRESS_TIMEOUT,
            )
            response.raise_for_status()
            return Response(response.json())
        except RequestException as exc:
            logger.warning(
                "Error getting progress exception %s", exc, exc_info=sys.exc_info()
            )
            return Response([])

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
                # "project": ["exact"],
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
@method_decorator(anonymous_cache_control, name="retrieve")
@method_decorator(anonymous_cache_control, name="list")
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
        return document.notes.get_viewable(self.request.user, document).preload(
            self.request.user, self.request.query_params.get("expand", "")
        )

    @transaction.atomic
    def perform_create(self, serializer):
        """Specify the document, user and organization"""
        serializer.save(
            document_id=self.kwargs["document_pk"],
            user=self.request.user,
            organization=self.request.user.organization,
        )
        transaction.on_commit(
            lambda: solr_index.delay(
                self.kwargs["document_pk"], field_updates={"notes": "set"}
            )
        )

    @transaction.atomic
    def perform_update(self, serializer):
        """Index the note changes in Solr"""
        super().perform_update(serializer)
        transaction.on_commit(
            lambda: solr_index.delay(
                self.kwargs["document_pk"], field_updates={"notes": "set"}
            )
        )

    @transaction.atomic
    def perform_destroy(self, instance):
        """Index the note changes in Solr"""
        super().perform_destroy(instance)
        transaction.on_commit(
            lambda: solr_index.delay(
                self.kwargs["document_pk"], field_updates={"notes": "set"}
            )
        )

    class Filter(django_filters.FilterSet):
        class Meta:
            model = Note
            fields = ["page_number"]

    filterset_class = Filter


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
class LegacyEntityViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = LegacyEntitySerializer
    queryset = LegacyEntity.objects.none()

    def get_queryset(self):
        """Only fetch documents viewable to this user"""
        document = get_object_or_404(
            Document.objects.get_viewable(self.request.user),
            pk=self.kwargs["document_pk"],
        )
        return document.legacy_entities.all()


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
    lookup_value_regex = DATA_KEY_REGEX

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
            Document.objects.get_viewable(self.request.user).select_for_update(),
            pk=self.kwargs["document_pk"],
        )
        if not self.request.user.has_perm("documents.change_document", document):
            self.permission_denied(self.request, "You may not edit this document")
        return document

    def create(self, request, *args, **kwargs):
        with transaction.atomic():

            document = self.get_object()

            serializer = self.get_serializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=True)

            if document.processing:
                return Response(
                    {"error": "Already processing"}, status=status.HTTP_400_BAD_REQUEST
                )

            document.status = Status.pending
            # we must invalidate the cache after a redaction
            document.cache_dirty = True
            document.save()
            transaction.on_commit(
                lambda: solr_index.delay(document.pk, field_updates={"status": "set"})
            )

        redact.delay(
            document.pk,
            document.slug,
            document.access,
            Language.get_choice(document.language).ocr_code,
            serializer.data,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@method_decorator(conditional_cache_control(no_cache=True), name="dispatch")
class EntityViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = EntityOccurrenceSerializer
    queryset = EntityOccurrence.objects.none()

    @lru_cache()
    def get_queryset(self):
        """Only fetch documents viewable to this user"""
        self.document = get_object_or_404(
            Document.objects.get_viewable(self.request.user),
            pk=self.kwargs["document_pk"],
        )
        return self.document.entities.all()

    def create(self, request, *args, **kwargs):
        """Initiate asyncrhonous creation of entities"""
        # pylint: disable=unused-argument
        if not request.user.has_perm("documents.change_document", self.document):
            raise exceptions.PermissionDenied(
                "You do not have permission to edit this document"
            )

        with transaction.atomic():
            # We select for update here to lock the document between checking if it is
            # processing and starting the entity extraction to ensure another
            # thread does not start processing this document before we mark it as
            # processing
            document = Document.objects.select_for_update().get(pk=self.document.pk)

            if document.processing:
                return Response(
                    {"error": "Already processing"}, status=status.HTTP_400_BAD_REQUEST
                )

            if document.entities.exists():
                return Response(
                    {"error": "Entities already created"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            document.status = Status.readable
            document.save()
            transaction.on_commit(
                lambda: solr_index.delay(document.pk, field_updates={"status": "set"})
            )

            transaction.on_commit(lambda: extract_entities.delay(self.document.pk))

        return Response("OK")

    def bulk_destroy(self, request, *args, **kwargs):
        """Delete all entities for the document"""
        # pylint: disable=unused-argument
        if request.user.has_perm("documents.change_document", self.document):
            self.document.entities.all().delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            raise exceptions.PermissionDenied(
                "You do not have permission to edit this document"
            )

    class Filter(django_filters.FilterSet):
        kind = ChoicesFilter(field_name="entity__kind", choices=EntityKind)
        occurrences = ChoicesFilter(method="occurrence_filter", choices=OccurrenceKind)
        mid = django_filters.BooleanFilter(
            method="value_exists", field_name="entity__mid", label="Has MID"
        )
        wikipedia_url = django_filters.BooleanFilter(
            method="value_exists",
            field_name="entity__wikipedia_url",
            label="Has Wikipedia URL",
        )

        def occurrence_filter(self, queryset, name, values):
            # pylint: disable=unused-argument
            query = Q()
            for value in values:
                query |= Q(occurrences__contains=[{"kind": value}])
            return queryset.filter(query)

        def value_exists(self, queryset, name, value):
            if value is True:
                return queryset.exclude(**{name: ""})
            elif value is False:
                return queryset.filter(**{name: ""})
            else:
                return queryset

        class Meta:
            model = EntityOccurrence
            fields = {
                # "kind": ["exact"],
                "occurrences": ["exact"],
                "relevance": ["gt"],
                # "mid": ["exact"],
                # "wikipedia_url": ["exact"],
            }

    filterset_class = Filter


# Used to map modification rotations to note rotations
ANGLE_TABLE = {"": 0, "cc": 1, "hw": 2, "ccw": 3}


@method_decorator(conditional_cache_control(no_cache=True), name="dispatch")
class ModificationViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = ModificationSpecSerializer
    permission_classes = (IsAuthenticated | DocumentPostProcessPermissions,)

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
        serializer = self.get_serializer(data={"data": request.data})
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            # We select for update here to lock the document between checking if it is
            # processing and starting the page modification to ensure another
            # thread does not start processing this document before we mark it as
            # processing
            document = Document.objects.select_for_update().get(pk=document.pk)

            if document.processing:
                return Response(
                    {"error": "Already processing"}, status=status.HTTP_400_BAD_REQUEST
                )

            document.status = Status.pending
            document.save()
            transaction.on_commit(
                lambda: solr_index.delay(document.pk, field_updates={"status": "set"})
            )

        modify.delay(
            document.pk,
            document.page_count,
            document.slug,
            document.access,
            serializer.data,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    @action(detail=False, methods=["post"])
    def post_process(self, request, document_pk=None):
        """Post-process after modifications are in place"""
        if "processing" not in self.request.auth["permissions"]:
            raise exceptions.PermissionDenied(
                "You do not have permission to post-process modifications"
            )

        post_process.delay(document_pk, request.data)

        return Response("OK", status=status.HTTP_200_OK)
