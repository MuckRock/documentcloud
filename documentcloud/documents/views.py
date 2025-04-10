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
from drf_spectacular.openapi import OpenApiParameter
from drf_spectacular.utils import OpenApiExample, extend_schema
from requests.exceptions import RequestException
from rest_flex_fields import FlexFieldsModelViewSet
from rest_flex_fields.utils import split_levels

# DocumentCloud
from documentcloud.addons.choices import Event
from documentcloud.addons.models import AddOnEvent
from documentcloud.common.environment import httpsub
from documentcloud.core.filters import ChoicesFilter, ModelMultipleChoiceFilter
from documentcloud.core.permissions import (
    DjangoObjectPermissionsOrAnonReadOnly,
    DocumentErrorTokenPermissions,
    DocumentPostProcessPermissions,
    DocumentTokenPermissions,
)
from documentcloud.core.utils import (  # pylint:disable=unused-import
    ProcessingTokenAuthenticationScheme,
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
    set_page_text,
    solr_delete_note,
    solr_index_note,
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

# pylint: disable=too-many-lines, line-too-long


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

    @extend_schema(operation_id="documents_bulk_partial_update")
    def bulk_partial_update(self, request, *args, **kwargs):
        return super().bulk_partial_update(request, *args, **kwargs)

    @extend_schema(operation_id="documents_bulk_update")
    def bulk_update(self, request, *args, **kwargs):
        return super().bulk_update(request, *args, **kwargs)

    @extend_schema(operation_id="documents_bulk_destroy")
    def bulk_destroy(self, request, *args, **kwargs):
        return super().bulk_destroy(request, *args, **kwargs)

    @extend_schema(
        responses={200: DocumentSerializer},
        examples=[
            OpenApiExample(
                "List Documents",
                description="A response from a request to retrieve a list of documents.",
                value=[
                    {
                        "id": 1,
                        "access": "public",
                        "admin_noindex": False,
                        "asset_url": "https://s3.documentcloud.org/",
                        "canonical_url": "https://www.documentcloud.org/documents/1-a-i-g-bailout-the-inspector-generals-report/",
                        "created_at": "2010-02-22T19:48:08.738905Z",
                        "description": "Neil Barofsky's report concludes that officials overseeing the rescue of the American International Group might have overpaid other banks to wrap up A.I.G.'s financial obligations.",
                        "edit_access": True,
                        "file_hash": "",
                        "noindex": False,
                        "language": "eng",
                        "organization": 1,
                        "original_extension": "pdf",
                        "page_count": 47,
                        "page_spec": "612.0x792.0:0-46",
                        "projects": [46386],
                        "publish_at": None,
                        "published_url": "",
                        "related_article": "",
                        "revision_control": False,
                        "slug": "a-i-g-bailout-the-inspector-generals-report",
                        "source": "Office of the Special Inspector General for T.A.R.P.",
                        "status": "success",
                        "title": "A.I.G. Bailout: The Inspector General's Report",
                        "updated_at": "2020-11-10T16:23:31.154198Z",
                        "user": 1,
                    },
                    {
                        "id": 2,
                        "access": "public",
                        "admin_noindex": False,
                        "asset_url": "https://s3.documentcloud.org/",
                        "canonical_url": "https://www.documentcloud.org/documents/2-president-obamas-health-care-proposal/",
                        "created_at": "2010-02-22T19:57:44.131650Z",
                        "description": "On Feb. 22, 2010, the Obama Administration released a detailed proposal outlining the President's plan for a compromise among the House and Senate versions of a health care bill, and Republican concerns.",
                        "edit_access": True,
                        "file_hash": "",
                        "noindex": False,
                        "language": "eng",
                        "organization": 1,
                        "original_extension": "pdf",
                        "page_count": 11,
                        "page_spec": "612.0x792.0:0-10",
                        "projects": [],
                        "publish_at": None,
                        "published_url": "",
                        "related_article": "",
                        "revision_control": False,
                        "slug": "president-obamas-health-care-proposal",
                        "source": "whitehouse.gov",
                        "status": "success",
                        "title": "President Obama's Health Care Proposal",
                        "updated_at": "2020-11-10T16:23:31.180653Z",
                        "user": 1,
                    },
                ],
            )
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        responses={200: DocumentSerializer},
        examples=[
            OpenApiExample(
                "Retrieve Document",
                description="A response from a request to retrieve an existing document.",
                value={
                    "id": 1,
                    "access": "public",
                    "admin_noindex": False,
                    "asset_url": "https://s3.documentcloud.org/",
                    "canonical_url": "https://www.documentcloud.org/documents/1-a-i-g-bailout-the-inspector-generals-report/",
                    "created_at": "2010-02-22T19:48:08.738905Z",
                    "data": {},
                    "description": "Neil Barofsky's report concludes that officials overseeing the rescue of the American International Group might have overpaid other banks to wrap up A.I.G.'s financial obligations.",
                    "edit_access": True,
                    "file_hash": "",
                    "noindex": False,
                    "language": "eng",
                    "organization": 1,
                    "original_extension": "pdf",
                    "page_count": 47,
                    "page_spec": "612.0x792.0:0-46",
                    "projects": [46386],
                    "publish_at": None,
                    "published_url": "",
                    "related_article": "",
                    "revision_control": False,
                    "slug": "a-i-g-bailout-the-inspector-generals-report",
                    "source": "Office of the Special Inspector General for T.A.R.P.",
                    "status": "success",
                    "title": "A.I.G. Bailout: The Inspector General's Report",
                    "updated_at": "2020-11-10T16:23:31.154198Z",
                    "user": 1,
                },
            )
        ],
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        request=DocumentSerializer,
        responses={201: DocumentSerializer},
        examples=[
            OpenApiExample(
                "Create Document",
                description="A request to create a new document by a file URL.",
                value={
                    "title": "New Document Title",
                    "file_url": "https://example.com/path/to/document.pdf",
                    "access": "public",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Create Document Response",
                description="Response when a document is successfully created.",
                value={
                    "id": 1,
                    "access": "public",
                    "asset_url": "https://s3.documentcloud.org/",
                    "canonical_url": "https://www.documentcloud.org/documents/1-new-document-slug/",
                    "created_at": "2025-02-16T00:00:00.000000Z",
                    "description": "",
                    "edit_access": True,
                    "file_hash": "",
                    "file_url": "https://example.com/path/to/document.pdf",
                    "language": "eng",
                    "noindex": False,
                    "original_extension": "pdf",
                    "page_count": 10,
                    "projects": [],
                    "publish_at": "",
                    "published_url": "",
                    "related_article": "",
                    "revision_control": False,
                    "slug": "new-document-slug",
                    "source": "",
                    "status": "success",
                    "title": "New Document Title",
                    "updated_at": "2025-02-16T00:00:00.000000Z",
                    "user": 1,
                },
            ),
        ],
    )
    def create(self, request, *args, **kwargs):
        """
        There are two supported ways to upload documents — directly uploading the file to our storage servers
        or by providing a URL to a publicly available PDF or other supported file type.
        To upload another supported file type you will need to include the original_extension field documented above.

        <strong> Direct File Upload Flow </strong>

        POST /api/documents/

        To initiate an upload, you will first create the document. You may specify all writable document fields
        (besides file_url). The response will contain all the fields for the document, with two being of note
        for this flow: presigned_url and id.

        If you would like to upload files in bulk, you may POST a list of JSON objects to /api/documents/ instead of a single object.
        The response will contain a list of document objects.

        PUT <presigned_url>

        Next, you will PUT the binary data for the file to the given presigned_url.
        The presigned URL is valid for 5 minutes.
        You may obtain a new URL by issuing a GET request to /api/documents/document_id/.

        If you are bulk uploading, you will still need to issue a single PUT to the corresponding presigned_url for each file.

        POST /api/documents/document_id/process/

        Finally, you will begin processing of the document.
        Note that this endpoint accepts only one optional parameter — force_ocr which, if set to true,
        will OCR the document even if it contains embedded text.

        If you are uploading in bulk you can issue a
        single POST to /api/document/process/ which will begin processing in bulk.
        You should pass a list of objects containing the document IDs
        of the documents you would like to being processing. You may optionally specify force_ocr for each document.



        <strong> URL Upload Flow </strong>

        POST /api/documents/

        If you set file_url to a URL pointing to a publicly accessible PDF,
        our servers will fetch the PDF and begin processing it automatically.

        You may also send a list of document objects with file_url set to bulk upload files using this flow.

        """
        return super().create(request, *args, **kwargs)

    def get_queryset(self):
        valid_token = (
            hasattr(self.request, "auth")
            and self.request.auth is not None
            and "processing" in self.request.auth.get("permissions", [])
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
            ocr_engines = [
                d.pop("ocr_engine", "tess4") for d in serializer.validated_data
            ]
        else:
            file_urls = [serializer.validated_data.pop("file_url", None)]
            force_ocrs = [serializer.validated_data.pop("force_ocr", False)]
            ocr_engines = [serializer.validated_data.pop("ocr_engine", "tess4")]

        documents = serializer.save(
            user=self.request.user, organization=self.request.user.organization
        )

        if not bulk:
            documents = [documents]

        for document, file_url, force_ocr, ocr_engine in zip(
            documents, file_urls, force_ocrs, ocr_engines
        ):
            document.index_on_commit()
            if file_url is not None:
                transaction.on_commit(
                    # fmt: off
                    lambda d=document, fu=file_url, fo=force_ocr, oe=ocr_engine:
                    fetch_file_url.delay(
                        fu, d.pk, fo, oe
                    )
                    # fmt: on
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
            serializer = ProcessDocumentSerializer(
                document, data=request.data, context=self.get_serializer_context()
            )
            serializer.is_valid(raise_exception=True)
            if document.status == Status.nofile:
                # create an initial revision only if this is the initial processing,
                # ie it was in status nofile before this
                # A revision will be made post processing whether this is the
                # initial processing or not
                document.create_revision(document.user.pk, "Initial", copy=True)
            document.status = Status.pending
            document.save()
            self._process(
                document,
                serializer.validated_data["force_ocr"],
                serializer.validated_data["ocr_engine"],
            )
            return Response("OK", status=status.HTTP_200_OK)

    @extend_schema(operation_id="documents_process_bulk_create")
    @transaction.atomic
    @action(detail=False, url_path="process", methods=["post"])
    def bulk_process(self, request):
        """Bulk process documents"""
        if "ids" in request.data:
            data = [{"id": i} for i in request.data["ids"]]
        else:
            data = request.data
        serializer = ProcessDocumentSerializer(
            self.filter_queryset(self.get_queryset()),
            data=data,
            context=self.get_serializer_context(),
            many=True,
            bulk=True,
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
        ocr_engine = {
            d["id"]: d.get("ocr_engine", "tess4") for d in serializer.validated_data
        }

        for document in documents:
            self._process(document, force_ocr[document.pk], ocr_engine[document.pk])
            if document.status == Status.nofile:
                # create an initial revision only if this is the initial processing,
                # ie it was in status nofile before this
                # A revision will be made post processing whether this is the
                # initial processing or not
                document.create_revision(document.user.pk, "Initial", copy=True)
        documents.update(status=Status.pending)
        return Response("OK", status=status.HTTP_200_OK)

    def _check_process(self, document):
        """Check the document is in a suitable state for processing"""

        if not self.request.user.has_perm("documents.change_document", document):
            return f"You do not have permission to edit document {document.pk}"

        if document.processing:
            return f"Already processing: {document.pk}"

        return None

    def _process(self, document, force_ocr, ocr_engine):
        """Process a document after you have uploaded the file"""
        transaction.on_commit(
            lambda: process.delay(
                document.pk,
                self.request.user.pk,
                self.request.user.organization.pk,
                force_ocr,
                ocr_engine,
            )
        )
        document.index_on_commit(field_updates={"status": "set"})

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
            document.index_on_commit(field_updates={"status": "set"})
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

    def _update_validate_processing(self, instances, validated_datas):
        """
        Validate properties which cannot be edit while processing
        after instances have been filtered
        """
        for instance, validated_data in zip(instances, validated_datas):
            # disallow access and page text changes while processing
            for prop in ("access", "pages"):
                if prop in validated_data and instance.processing:
                    raise serializers.ValidationError(
                        _(
                            f"You may not update `{prop}` while the document "
                            "is processing"
                        )
                    )

    @transaction.atomic
    def perform_update(self, serializer):
        # work for regular and bulk updates

        logger.info("[DOC UPDATE] start perform update")

        bulk = getattr(serializer, "many", False)
        logger.info("[DOC UPDATE] bulk %s", bulk)

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

        logger.info("[DOC UPDATE] instances: %s", [i.pk for i in instances])
        self._update_validate_processing(instances, validated_datas)

        old_accesses = [i.access for i in instances]
        old_processings = [i.processing for i in instances]
        old_data_keys = [i.data.keys() for i in instances]
        old_revision_controls = [i.revision_control for i in instances]
        logger.info("[DOC UPDATE] do perform")
        super().perform_update(serializer)

        # refresh from database after performing update
        if bulk:
            instances = sorted(serializer.instance, key=lambda i: i.id)
        else:
            instances = [serializer.instance]

        logger.info("[DOC UPDATE] pre-loop")

        for (
            instance,
            validated_data,
            old_access,
            old_processing,
            old_data_key,
            old_revision_control,
        ) in zip(
            instances,
            validated_datas,
            old_accesses,
            old_processings,
            old_data_keys,
            old_revision_controls,
        ):

            self._update_access(instance, old_access, validated_data)
            self._update_solr(instance, old_processing, old_data_key, validated_data)
            self._update_cache(instance, old_processing)
            self._run_addons(instance, old_processing)
            self._set_page_text(instance, validated_data.get("pages"))
            self._create_revision(instance, old_processing, old_revision_control)

    def _update_access(self, document, old_access, validated_data):
        """Update the access of a document after it has been updated"""
        logger.info("[DOC UPDATE] update access %s", document.pk)
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
        logger.info("[DOC UPDATE] update solr %s", document.pk)
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
            if data is not None:
                # we want to update all data keys if data is set directly,
                # including old data keys which may have been removed
                all_keys = old_data_keys | data.keys()
                for key in all_keys:
                    validated_data[f"data_{key}"] = None

            kwargs = {"field_updates": {f: "set" for f in validated_data}}

        document.index_on_commit(**kwargs)

    def _update_cache(self, document, old_processing):
        """Invalidate the cache when finished processing a detructive operation"""
        logger.info("[DOC UPDATE] update cache %s", document.pk)
        if old_processing and not document.processing and document.cache_dirty:
            transaction.on_commit(lambda: invalidate_cache.delay(document.pk))

    def _run_addons(self, document, old_processing):
        """Run upload add-ons once the document is succesfully processed"""
        logger.info("[DOC UPDATE] run addons %s", document.pk)
        if old_processing and document.status == Status.success:
            events = AddOnEvent.objects.filter(
                event=Event.upload,
                user=document.user,
            )
            if events:
                logger.info(
                    "[DISPATCHING EVENTS] upload doc: %s events: %d",
                    document.pk,
                    len(events),
                )
            for event in events:
                event.dispatch(document_pk=document.pk)

    def _set_page_text(self, document, pages):
        logger.info("[DOC UPDATE] set page text %s", document.pk)
        if pages is not None:
            set_page_text.delay(document.pk, pages)

    def _create_revision(self, document, old_processing, old_revision_control):
        # create an intial revision when revision control is turned on
        logger.info("[DOC UPDATE] create revision %s", document.pk)
        if not old_revision_control and document.revision_control:
            if document.revisions.exists():
                comment = "Re-enable"
            else:
                comment = "Enable"
            document.create_revision(self.request.user.pk, comment, copy=True)

        # if revision control is turned on and we finished processing succesfully,
        # copy the PDF to the latest revision
        if (
            document.revision_control
            and old_processing
            and document.status == Status.success
        ):
            last_revision = document.revisions.last()
            if last_revision:
                last_revision.copy()

    @extend_schema(operation_id="documents_search_across")
    @action(detail=False, methods=["get"])
    def search(self, request):
        """Search across all documents on DocumentCloud"""
        if settings.SOLR_DISABLE_ANON and request.user.is_anonymous:
            return Response(
                {
                    "error": "Anonymous searching has been disabled due to server load",
                    "code": "anon disabled",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
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
        except ValueError as exc:
            return Response(
                {"error": exc.args[0], "code": "max_page"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        else:
            return Response(response)

    @extend_schema(operation_id="documents_search_within_single_document")
    @action(detail=True, url_path="search", methods=["get"])
    def page_search(self, request, pk=None):
        """Search within a single document"""
        if settings.SOLR_DISABLE_ANON and request.user.is_anonymous:
            return Response(
                {
                    "error": "Anonymous searching has been disabled due to server load",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
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

    @action(detail=False, methods=["get"], url_path="pending")
    def bulk_pending(self, request):
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

    @action(detail=True, methods=["get"], url_path="pending")
    def pending(self, request, pk=None):  # pylint:disable = unused-argument
        """Get the processing progress of a single pending document"""
        document = self.get_object()

        if not request.user.is_authenticated or document.user != request.user:
            return Response({})

        if document.status != Status.pending:
            return Response({})

        try:
            response = httpsub.post(
                settings.PROGRESS_URL,
                json={"doc_ids": [document.id]},
                timeout=settings.PROGRESS_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            return Response(data[0] if data else {})
        except RequestException as exc:
            logger.warning(
                "Error getting progress for document %s: %s",
                document.id,
                exc,
                exc_info=sys.exc_info(),
            )
            return Response({})


    class Filter(django_filters.FilterSet):
        user = ModelMultipleChoiceFilter(model=User, help_text="Filter by users")
        organization = ModelMultipleChoiceFilter(
            model=Organization,
            help_text="Filter by which organization the document belongs to",
        )
        project = ModelMultipleChoiceFilter(
            model=Project,
            field_name="projects",
            help_text=("Filter by which projects a document belongs to"),
        )
        access = ChoicesFilter(choices=Access)
        status = ChoicesFilter(choices=Status)

        class Meta:
            model = Document
            fields = {
                "user": ["exact"],
                "organization": ["exact"],
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

    @extend_schema(tags=["document_errors"])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(tags=["document_errors"])
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @lru_cache()
    def get_queryset(self):
        """Only fetch documents viewable to this user"""
        valid_token = (
            hasattr(self.request, "auth")
            and self.request.auth is not None
            and "processing" in self.request.auth.get("permissions", [])
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
        self.document.index_on_commit(field_updates={"status": "set"})


@method_decorator(conditional_cache_control(no_cache=True), name="dispatch")
@method_decorator(anonymous_cache_control, name="retrieve")
@method_decorator(anonymous_cache_control, name="list")
class NoteViewSet(FlexFieldsModelViewSet):
    serializer_class = NoteSerializer
    permit_list_expands = ["user", "organization"]
    queryset = Note.objects.none()

    @extend_schema(tags=["document_notes"])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(tags=["document_notes"])
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(tags=["document_notes"])
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(tags=["document_notes"])
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @extend_schema(tags=["document_notes"])
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @extend_schema(tags=["document_notes"])
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

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
        note = serializer.save(
            document_id=self.kwargs["document_pk"],
            user=self.request.user,
            organization=self.request.user.organization,
        )
        if settings.SOLR_INDEX_NOTES:
            transaction.on_commit(lambda: solr_index_note.delay(note.pk))

    @transaction.atomic
    def perform_update(self, serializer):
        """Index the note changes in Solr"""
        note = serializer.save()
        if settings.SOLR_INDEX_NOTES:
            transaction.on_commit(lambda: solr_index_note.delay(note.pk))

    @transaction.atomic
    def perform_destroy(self, instance):
        """Index the note changes in Solr"""
        note_pk = instance.pk
        super().perform_destroy(instance)
        if settings.SOLR_INDEX_NOTES:
            transaction.on_commit(lambda: solr_delete_note.delay(note_pk))

    class Filter(django_filters.FilterSet):
        class Meta:
            model = Note
            fields = ["page_number"]

    filterset_class = Filter


@method_decorator(conditional_cache_control(no_cache=True), name="dispatch")
class SectionViewSet(viewsets.ModelViewSet):
    serializer_class = SectionSerializer
    queryset = Section.objects.none()

    @extend_schema(tags=["document_sections"])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(tags=["document_sections"])
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(tags=["document_sections"])
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(tags=["document_sections"])
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @extend_schema(tags=["document_sections"])
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @extend_schema(tags=["document_sections"])
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

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


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="document_pk",
            type=int,
            description="The ID of the document",
            required=True,
            location=OpenApiParameter.PATH,
        )
    ]
)
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

    @extend_schema(tags=["document_data"])
    def list(self, request, document_pk=None):
        document = self.get_object()
        return Response(document.data)

    @extend_schema(tags=["document_data"])
    def retrieve(self, request, pk=None, document_pk=None):
        document = self.get_object()
        return Response(document.data.get(pk))

    @extend_schema(tags=["document_data"])
    @transaction.atomic
    def update(self, request, pk=None, document_pk=None):
        document = self.get_object(edit=True)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        # remove duplicate values
        document.data[pk] = list(set(serializer.data["values"]))
        document.save()
        document.index_on_commit(field_updates={f"data_{pk}": "set"})
        return Response(document.data)

    @extend_schema(tags=["document_data"])
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
        document.index_on_commit(field_updates={f"data_{pk}": "set"})
        return Response(document.data)

    @extend_schema(tags=["document_data"])
    @transaction.atomic
    def destroy(self, request, pk=None, document_pk=None):
        document = self.get_object(edit=True)

        if pk in document.data:
            del document.data[pk]
            document.save()
            document.index_on_commit(field_updates={f"data_{pk}": "set"})

        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="document_pk",
            type=int,
            description="The ID of the document",
            required=True,
            location=OpenApiParameter.PATH,
        )
    ]
)
@method_decorator(conditional_cache_control(no_cache=True), name="dispatch")
class RedactionViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = RedactionSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        # Just check if we have view permissions
        get_object_or_404(
            Document.objects.get_viewable(self.request.user).values_list("pk"),
            pk=self.kwargs["document_pk"],
        )
        # Then reload with select_for_update - cannot do in one call since
        # get_viewable has a distinct clause which cannot be run with select
        # for update
        document = Document.objects.select_for_update().get(
            pk=self.kwargs["document_pk"]
        )
        if not self.request.user.has_perm("documents.change_document", document):
            self.permission_denied(self.request, "You may not edit this document")
        return document

    @extend_schema(tags=["document_redactions"])
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
            document.index_on_commit(field_updates={"status": "set"})

        redact.delay(
            document.pk,
            self.request.user.pk,
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
        return self.document.legacy_entities_2.all()

    def create(self, request, *args, **kwargs):
        """Initiate asyncrhonous creation of entities"""
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

            if document.legacy_entities_2.exists():
                return Response(
                    {"error": "Entities already created"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            document.status = Status.readable
            document.save()
            document.index_on_commit(field_updates={"status": "set"})

            transaction.on_commit(lambda: extract_entities.delay(self.document.pk))

        return Response("OK")

    def bulk_destroy(self, request, *args, **kwargs):
        """Delete all entities for the document"""
        if request.user.has_perm("documents.change_document", self.document):
            self.document.legacy_entities_2.all().delete()
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


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="document_pk",
            type=int,
            description="The ID of the document",
            required=True,
            location=OpenApiParameter.PATH,
        )
    ]
)
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

    @extend_schema(tags=["document_modifications"])
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
            document.index_on_commit(field_updates={"status": "set"})

        modify.delay(
            document.pk,
            self.request.user.pk,
            serializer.data,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=["document_modifications"])
    @transaction.atomic
    @action(detail=False, methods=["post"])
    def post_process(self, request, document_pk=None):
        """Post-process after modifications are in place"""
        if "processing" not in self.request.auth.get("permissions", []):
            raise exceptions.PermissionDenied(
                "You do not have permission to post-process modifications"
            )

        post_process.delay(document_pk, request.data)

        return Response("OK", status=status.HTTP_200_OK)
