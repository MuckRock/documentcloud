# pylint:disable = too-many-lines

# Django
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.postgres.aggregates.general import StringAgg
from django.db import transaction
from django.db.models import Q
from django.db.models.aggregates import Count
from django.db.models.expressions import Case, Exists, F, OuterRef, Value, When
from django.db.models.fields.related import ForeignKey
from django.db.models.functions.text import Concat
from django.http.response import (
    Http404,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

# Standard Library
import hashlib
import hmac
import json
import logging
from collections import defaultdict
from datetime import timedelta
from functools import lru_cache

# Third Party
import requests
from django_filters import rest_framework as django_filters
from django_filters.rest_framework.backends import DjangoFilterBackend
from drf_spectacular.utils import OpenApiExample, extend_schema
from furl import furl
from rest_flex_fields import FlexFieldsModelViewSet
from rest_flex_fields.utils import is_expanded

# DocumentCloud
from documentcloud.addons.choices import Event
from documentcloud.addons.models import (
    AddOn,
    AddOnEvent,
    AddOnRun,
    GitHubAccount,
    GitHubInstallation,
    VisualAddOn,
)
from documentcloud.addons.serializers import (
    AddOnEventSerializer,
    AddOnRunSerializer,
    AddOnSerializer,
)
from documentcloud.addons.tasks import cancel, dispatch, update_config
from documentcloud.common.environment import storage
from documentcloud.core.filters import ModelChoiceFilter, QueryArrayWidget

logger = logging.getLogger(__name__)


class AddOnViewSet(viewsets.ModelViewSet):
    serializer_class = AddOnSerializer
    queryset = AddOn.objects.none()

    @extend_schema(
        request=AddOnRunSerializer,
        responses={201: AddOnRunSerializer},
        examples=[
            OpenApiExample(
                "Create Request",
                description="An example request for creating a new Add-On.",
                value={
                    "addon": 11,
                    "progress": 50,
                    "message": "Exporting notes...",
                    "file_name": "notes-export.zip",
                    "dismissed": False,
                    "parameters": {},
                    "rating": None,
                    "comment": "Export in progress",
                    "credits_spent": 0,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Create Response",
                description="An example response for creating a new Add-On.",
                value={
                    "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "addon": 11,
                    "user": 20080,
                    "status": "in_progress",
                    "progress": 50,
                    "message": "Exporting notes...",
                    "file_url": "https://example.com/note-export.zip",
                    "file_expires_at": "2025-02-20T12:34:56Z",
                    "dismissed": False,
                    "rating": None,
                    "comment": "Export in progress",
                    "credits_spent": 0,
                    "created_at": "2025-02-16T10:00:00Z",
                    "updated_at": "2025-02-16T10:15:00Z",
                },
                response_only=True,
            ),
        ],
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(
        responses={200: AddOnRunSerializer},
        examples=[
            OpenApiExample(
                "List Add-On Runs",
                description="An example response for listing Add-Ons.",
                value=[
                    {
                        "id": 8,
                        "user": 20080,
                        "organization": 125,
                        "access": "public",
                        "name": "Bulk Edit",
                        "repository": "MuckRock/documentcloud-bulk-edit-addon",
                        "parameters": {
                            "type": "object",
                            "title": "Bulk Edit",
                            "version": 2,
                            "documents": ["query"],
                            "categories": ["bulk"],
                            "properties": {
                                "source": {"type": "string", "title": "Source"},
                                "description": {
                                    "type": "string",
                                    "title": "Description",
                                },
                                "published_url": {
                                    "type": "string",
                                    "title": "Published URL",
                                    "format": "uri",
                                },
                                "related_article": {
                                    "type": "string",
                                    "title": "Related Article URL",
                                    "format": "uri",
                                },
                            },
                            "description": (
                                "<p>This will update document information for all"
                                " documents in your current search. Please be sure you"
                                " have edit access to these documents before running"
                                " this add-on.</p>"
                            ),
                            "instructions": "",
                        },
                        "created_at": "2022-04-20T13:44:49.028548Z",
                        "updated_at": "2025-02-13T18:20:04.256135Z",
                        "active": True,
                        "default": False,
                        "featured": False,
                    },
                    {
                        "id": 9,
                        "user": 20080,
                        "organization": 125,
                        "access": "public",
                        "name": "Regex Extractor",
                        "repository": "MuckRock/documentcloud-regex-addon",
                        "parameters": {
                            "type": "object",
                            "title": "Regex Extractor",
                            "required": ["regex"],
                            "documents": ["selected", "query"],
                            "categories": ["extraction"],
                            "properties": {
                                "key": {
                                    "type": "string",
                                    "title": "Key",
                                    "default": "_tag",
                                    "description": (
                                        "Use a key-value pair, where your regex match"
                                        " is the value and you set the key. Keep _tag"
                                        " if you want the regular expression match to"
                                        ' appear as a standalone "tag" and not a'
                                        " key-value pair."
                                    ),
                                },
                                "regex": {
                                    "type": "string",
                                    "title": "Regex",
                                    "description": (
                                        "The regular expression that you would like to"
                                        " search your documents for."
                                    ),
                                },
                                "annotate": {
                                    "type": "boolean",
                                    "title": "Annotate",
                                    "default": False,
                                    "description": (
                                        "Annotate pages where regex matches are found."
                                    ),
                                },
                                "annotation_access": {
                                    "enum": [
                                        "private",
                                        "organization",
                                        "public",
                                    ],
                                    "type": "string",
                                    "title": "Access Level",
                                    "default": "private",
                                    "description": (
                                        "Access level for posted annotations with"
                                        " matches."
                                    ),
                                },
                            },
                            "description": (
                                "<p>Given a regular expression as input, this Add-On"
                                " searches through each document for matches. You can"
                                " choose to add &ldquo;tags&rdquo; or"
                                " &ldquo;key-value&rdquo; pairs to your document so"
                                " that the document is marked with the first instance"
                                " of the match that is found. This Add-On also outputs"
                                " a CSV that lists all matches found in a given"
                                " document and the page number the match was found on."
                                " This can be helpful for analysis or inspecting your"
                                " results</p>"
                            ),
                            "instructions": "",
                        },
                        "created_at": "2022-04-20T13:44:49.038381Z",
                        "updated_at": "2024-12-07T03:39:12.837192Z",
                        "active": False,
                        "default": False,
                        "featured": False,
                    },
                ],
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        responses={200: AddOnSerializer},
        examples=[
            OpenApiExample(
                "Retrieve Add-On",
                description="An example response for retrieving an Add-On.",
                value={
                    "id": 11,
                    "user": 20080,
                    "organization": 125,
                    "access": "public",
                    "name": "Note Exporter",
                    "repository": "MuckRock/documentcloud-note-export-addon",
                    "parameters": {
                        "type": "object",
                        "title": "Note Exporter",
                        "documents": ["selected", "query"],
                        "categories": ["export"],
                        "properties": {},
                        "description": (
                            "<p>Export notes from the selected documents as text files"
                            " in a zip file</p>"
                        ),
                        "instructions": "",
                    },
                    "created_at": "2022-04-20T13:44:49.055986Z",
                    "updated_at": "2024-12-03T16:09:50.426796Z",
                    "active": False,
                    "default": False,
                    "featured": False,
                },
            ),
        ],
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        request=AddOnSerializer,
        responses=AddOnSerializer,
        examples=[
            OpenApiExample(
                "Full Update Request",
                description="An example request for a full update of an add-on.",
                value={"active": True, "organization": 125},
                request_only=True,
            ),
            OpenApiExample(
                "Full Update Response",
                description="A response example after successfully updating an add-on.",
                value={
                    "id": 11,
                    "user": 20080,
                    "organization": 125,
                    "access": "public",
                    "name": "Note Exporter",
                    "repository": "MuckRock/documentcloud-note-export-addon",
                    "parameters": {
                        "type": "object",
                        "title": "Note Exporter",
                        "documents": ["selected", "query"],
                        "categories": ["export"],
                        "properties": {},
                        "description": (
                            "<p>Export notes from the selected documents as text files"
                            " in a zip file</p>"
                        ),
                        "instructions": "",
                    },
                    "created_at": "2022-04-20T13:44:49.055986Z",
                    "updated_at": "2025-02-16T12:34:56Z",
                    "active": True,
                    "default": False,
                    "featured": False,
                },
                response_only=True,
            ),
        ],
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @extend_schema(
        request=AddOnSerializer,
        responses=AddOnSerializer,
        examples=[
            OpenApiExample(
                "Partial Update Request",
                description="An example request for a partial update of an add-on.",
                value={"active": True},  # Only updating the 'active' field
                request_only=True,
            ),
            OpenApiExample(
                "Partial Update Response",
                description=(
                    "A response example after successfully performing a partial update"
                    " on an add-on."
                ),
                value={
                    "id": 11,
                    "user": 20080,
                    "organization": 125,
                    "access": "public",
                    "name": "Note Exporter",
                    "repository": "MuckRock/documentcloud-note-export-addon",
                    "parameters": {
                        "type": "object",
                        "title": "Note Exporter",
                        "documents": ["selected", "query"],
                        "categories": ["export"],
                        "properties": {},
                        "description": (
                            "<p>Export notes from the selected documents as text files"
                            " in a zip file</p>"
                        ),
                        "instructions": "",
                    },
                    "created_at": "2022-04-20T13:44:49.055986Z",
                    "updated_at": "2025-02-16T12:34:56Z",
                    "active": True,
                    "default": False,
                    "featured": False,
                },
                response_only=True,
            ),
        ],
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    def get_queryset(self):
        queryset = (
            AddOn.objects.get_viewable(self.request.user)
            .order_by("-pk")
            .select_related("github_account")
        )
        if self.request.user.is_authenticated:
            queryset = queryset.annotate(
                active=Exists(self.request.user.active_addons.filter(pk=OuterRef("pk")))
            )
        else:
            queryset = queryset.annotate(active=Value(False))
        return queryset

    def perform_update(self, serializer):
        super().perform_update(serializer)
        # add or remove to add-on from the current user's active add-ons
        # if needed
        if "active_w" not in serializer.validated_data:
            return
        addon = self.get_object()
        if serializer.validated_data["active_w"] and not addon.active:
            self.request.user.active_addons.add(addon)
        if not serializer.validated_data["active_w"] and addon.active:
            self.request.user.active_addons.remove(addon)
        # pylint: disable=pointless-statement, protected-access
        # data is a property, we call it here to populate _data
        serializer.data
        # we need to set _data directly to set the update value from active_w
        serializer._data["active"] = serializer.validated_data["active_w"]

    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def update_config(self, request):
        name = request.data.get("repository")
        if name:
            update_config.delay(name)
        return Response(status=status.HTTP_204_NO_CONTENT)

    class Filter(django_filters.FilterSet):
        active = django_filters.BooleanFilter(
            field_name="active", label="Add-On marked as active"
        )
        premium = django_filters.BooleanFilter(
            method="premium_filter", label="Add-On requires credits to run."
        )
        query = django_filters.CharFilter(method="query_filter", label="Query")
        category = django_filters.MultipleChoiceFilter(
            field_name="parameters",
            lookup_expr="categories__contains",
            label="Category",
            widget=QueryArrayWidget,
            choices=(
                ("export", "export"),
                ("ai", "ai"),
                ("bulk", "bulk"),
                ("extraction", "extraction"),
                ("file", "file"),
                ("monitor", "monitor"),
                ("statistical", "statistical"),
            ),
        )
        default = django_filters.BooleanFilter(
            field_name="default", label="Enabled by default"
        )
        featured = django_filters.BooleanFilter(
            field_name="featured",
            label="Marked as featured by the MuckRock team.",
        )
        repository = django_filters.CharFilter(
            label="Link to the Github repository for this Add-On"
        )

        def query_filter(self, queryset, name, value):
            # pylint: disable=unused-argument
            return queryset.filter(
                Q(name__icontains=value) | Q(parameters__description__icontains=value)
            )

        def category_filter(self, queryset, name, value):
            # pylint: disable=unused-argument
            query = Q()
            for value_ in value:
                query |= Q(parameters__categories__contains=value_)
            return queryset.filter(query)

        def premium_filter(self, queryset, name, value):
            # pylint: disable=unused-argument
            if value:
                return queryset.filter(
                    parameters__has_key="categories",
                    parameters__categories__contains="premium",
                )
            else:
                return queryset.exclude(
                    parameters__has_key="categories",
                    parameters__categories__contains="premium",
                )

        class Meta:
            model = AddOn
            fields = ["featured", "default", "repository", "premium"]

    filterset_class = Filter


class AddOnRunViewSet(FlexFieldsModelViewSet):
    serializer_class = AddOnRunSerializer
    queryset = AddOnRun.objects.none()
    lookup_field = "uuid"
    permit_list_expands = ["addon", "event"]
    filter_backends = [filters.OrderingFilter, DjangoFilterBackend]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    @extend_schema(
        request=None,
        responses={
            200: AddOnRunSerializer,
        },
        examples=[
            OpenApiExample(
                "List Add-On Runs",
                description=(
                    "A response for a request to retrieve a list of all add-on runs."
                ),
                value=[
                    {
                        "uuid": "267f4e1a-9b66-4feb-9347-77a15832023c",
                        "addon": 436,
                        "user": 102112,
                        "status": "success",
                        "progress": 0,
                        "message": "No changes detected on the site",
                        "file_url": None,
                        "file_expires_at": None,
                        "dismissed": True,
                        "rating": 0,
                        "comment": "",
                        "credits_spent": 0,
                        "created_at": "2025-02-16T00:10:00.244385Z",
                        "updated_at": "2025-02-16T00:10:18.774025Z",
                    },
                    {
                        "uuid": "fceef811-cf11-4be3-a22d-2e3e9f6c7e8b",
                        "addon": 436,
                        "user": 102112,
                        "status": "success",
                        "progress": 0,
                        "message": "No changes detected on the site",
                        "file_url": None,
                        "file_expires_at": None,
                        "dismissed": True,
                        "rating": 0,
                        "comment": "",
                        "credits_spent": 0,
                        "created_at": "2025-02-15T00:10:00.406270Z",
                        "updated_at": "2025-02-15T00:10:26.128542Z",
                    },
                ],
                response_only=True,
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=None,
        responses={
            200: AddOnRunSerializer,
        },
        examples=[
            OpenApiExample(
                "Retrieve Add-On Run",
                description="A request to retrieve details of a specific add-on run.",
                value={
                    "uuid": "267f4e1a-9b66-4feb-9347-77a15832023c",
                    "addon": 436,
                    "user": 102112,
                    "status": "success",
                    "progress": 0,
                    "message": "No changes detected on the site",
                    "file_url": None,
                    "file_expires_at": None,
                    "dismissed": True,
                    "rating": 0,
                    "comment": "",
                    "credits_spent": 0,
                    "created_at": "2025-02-16T00:10:00.244385Z",
                    "updated_at": "2025-02-16T00:10:18.774025Z",
                },
                response_only=True,
            ),
        ],
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        request=AddOnRunSerializer,
        responses={201: AddOnRunSerializer},
        examples=[
            OpenApiExample(
                "Create Add-On Run Request",
                description="A request to create a new add-on run.",
                value={
                    "addon": 436,
                    "parameters": {"param1": "value1"},
                    "credits_spent": 5,
                    "dismissed": True,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Create Add-On Run Response",
                description="A response after successfully creating an add-on run.",
                value={
                    "uuid": "267f4e1a-9b66-4feb-9347-77a15832023c",
                    "addon": 436,
                    "user": 102112,
                    "status": "queued",
                    "progress": 0,
                    "message": "Running the add-on...",
                    "file_url": None,
                    "file_expires_at": None,
                    "dismissed": True,
                    "rating": None,
                    "comment": "",
                    "credits_spent": 5,
                    "created_at": "2025-02-16T00:10:00.244385Z",
                    "updated_at": "2025-02-16T00:10:18.774025Z",
                },
                response_only=True,
            ),
        ],
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(
        request=AddOnRunSerializer,
        responses={200: AddOnRunSerializer},
        examples=[
            OpenApiExample(
                "Update Add-On Run Request",
                description="A request to update an existing add-on run.",
                value={
                    "status": "in_progress",
                    "progress": 50,
                    "message": "Processing...",
                    "dismissed": False,
                    "credits_spent": 10,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Update Add-On Run Response",
                description="A response after successfully updating an add-on run.",
                value={
                    "uuid": "267f4e1a-9b66-4feb-9347-77a15832023c",
                    "addon": 436,
                    "user": 102112,
                    "status": "in_progress",
                    "progress": 50,
                    "message": "Processing...",
                    "file_url": None,
                    "file_expires_at": None,
                    "dismissed": False,
                    "rating": 4,
                    "comment": "Good progress",
                    "credits_spent": 10,
                    "created_at": "2025-02-16T00:10:00.244385Z",
                    "updated_at": "2025-02-16T00:15:00.244385Z",
                },
                response_only=True,
            ),
        ],
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @extend_schema(
        request=AddOnRunSerializer,
        responses={200: AddOnRunSerializer},
        examples=[
            OpenApiExample(
                "Partial Update Add-On Run Request (Update Message Only)",
                description=(
                    "A request to partially update an existing add-on run by changing"
                    " only the message."
                ),
                value={
                    "message": "The process is almost complete!",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Partial Update Add-On Run Response (Message Updated)",
                description=(
                    "A response after successfully partially updating an add-on run"
                    " with the new message."
                ),
                value={
                    "uuid": "267f4e1a-9b66-4feb-9347-77a15832023c",
                    "addon": 436,
                    "user": 102112,
                    "status": "in_progress",
                    "progress": 50,
                    "message": "The process is almost complete!",
                    "file_url": None,
                    "file_expires_at": None,
                    "dismissed": False,
                    "rating": 4,
                    "comment": "Good progress",
                    "credits_spent": 10,
                    "created_at": "2025-02-16T00:10:00.244385Z",
                    "updated_at": "2025-02-16T00:15:00.244385Z",
                },
                response_only=True,
            ),
        ],
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @lru_cache()
    def get_queryset(self):
        """Only fetch add-on runs viewable to this user"""
        queryset = AddOnRun.objects.get_viewable(self.request.user)
        if is_expanded(self.request, "addon"):
            queryset = queryset.select_related("addon")
        return queryset

    def perform_create(self, serializer):
        with transaction.atomic():
            run = serializer.save(user=self.request.user)
            transaction.on_commit(
                lambda: dispatch.delay(
                    run.addon_id,
                    run.uuid,
                    self.request.user.pk,
                    self.request.data.get("documents"),
                    self.request.data.get("query"),
                    self.request.data["parameters"],
                )
            )

    def perform_destroy(self, instance):
        cancel.delay(instance.uuid)

    class Filter(django_filters.FilterSet):
        event = ModelChoiceFilter(
            model=AddOnEvent, help_text="Filter runs by a specific event ID."
        )
        addon = ModelChoiceFilter(
            model=AddOn, help_text="Filter runs by a specific add-on ID."
        )
        dismissed = django_filters.BooleanFilter(help_text="Was this run dismissed?")

        class Meta:
            model = AddOnRun
            fields = {
                "dismissed": ["exact"],
                "event": ["exact"],
                "addon": ["exact"],
            }

    filterset_class = Filter


class AddOnEventViewSet(FlexFieldsModelViewSet):
    serializer_class = AddOnEventSerializer
    queryset = AddOnEvent.objects.none()
    permit_list_expands = ["addon"]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    ordering_fields = ["id", "created_at", "updated_at"]
    ordering = ["-created_at"]

    @extend_schema(
        request=None,
        responses={
            200: AddOnEventSerializer,
        },
        examples=[
            OpenApiExample(
                "List Add-On Events",
                description=(
                    "A response to a request to retrieve a list of all add-on events"
                    " viewable by the user."
                ),
                value=[
                    {
                        "id": 616,
                        "addon": 436,
                        "user": 102112,
                        "parameters": {
                            "site": "https://github.com/duckduckgrayduck/pdf-splitter-add-on/issues",  # pylint:disable=line-too-long
                            "selector": "*",
                        },
                        "event": 0,
                        "scratch": {"timestamp": "20230703130357"},
                        "created_at": "2023-07-03T01:02:09.025856Z",
                        "updated_at": "2023-07-15T06:20:35.502166Z",
                    },
                    {
                        "id": 617,
                        "addon": 388,
                        "user": 102112,
                        "parameters": {
                            "site": "https://github.com/duckduckgrayduck/bulk-reprocress-addon/issues",  # pylint:disable=line-too-long
                            "selector": "*",
                        },
                        "event": 0,
                        "scratch": {},
                        "created_at": "2023-07-03T02:14:13.954076Z",
                        "updated_at": "2023-07-03T04:02:16.471265Z",
                    },
                ],
                response_only=True,
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=AddOnEventSerializer,
        responses={201: AddOnEventSerializer},
        examples=[
            OpenApiExample(
                "Create Add-On Event Request",
                description="A request to create a new add-on event.",
                value={
                    "addon": 436,
                    "parameters": {
                        "site": "https://github.com/duckduckgrayduck/pdf-splitter-add-on/issues",  # pylint:disable=line-too-long
                        "selector": "*",
                    },
                    "event": 1,
                    "scratch": {},
                },
                request_only=True,
            ),
            OpenApiExample(
                "Create Add-On Event Response",
                description="A response after successfully creating an add-on event.",
                value={
                    "id": 618,
                    "addon": 436,
                    "user": 102112,
                    "parameters": {
                        "site": "https://github.com/duckduckgrayduck/pdf-splitter-add-on/issues",  # pylint:disable=line-too-long
                        "selector": "*",
                    },
                    "event": 1,
                    "scratch": {},
                    "created_at": "2025-02-16T00:10:00.244385Z",
                    "updated_at": "2025-02-16T00:10:18.774025Z",
                },
                response_only=True,
            ),
        ],
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(
        request=None,
        responses={
            200: AddOnEventSerializer,
        },
        examples=[
            OpenApiExample(
                "Retrieve Add-On Event",
                description="A response to retrieve a specific add-on event by its ID.",
                value={
                    "id": 616,
                    "addon": 436,
                    "user": 102112,
                    "parameters": {
                        "site": "https://github.com/duckduckgrayduck/pdf-splitter-add-on/issues",  # pylint:disable=line-too-long
                        "selector": "*",
                    },
                    "event": 0,
                    "scratch": {"timestamp": "20230703130357"},
                    "created_at": "2023-07-03T01:02:09.025856Z",
                    "updated_at": "2023-07-15T06:20:35.502166Z",
                },
                response_only=True,
            ),
        ],
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        request=AddOnEventSerializer,
        responses={200: AddOnEventSerializer},
        examples=[
            OpenApiExample(
                "Update Add-On Event Request",
                description="A request to update an add-on event.",
                value={
                    "addon": 436,
                    "event": 0,
                    "scratch": {"timestamp": "20230810101000"},
                },
                request_only=True,
            ),
            OpenApiExample(
                "Update Add-On Event Response",
                description="A response after successfully updating an add-on event.",
                value={
                    "id": 616,
                    "addon": 436,
                    "user": 102112,
                    "parameters": {
                        "site": "https://github.com/duckduckgrayduck/pdf-splitter-add-on/issues",  # pylint:disable=line-too-long
                        "selector": "*",
                    },
                    "event": 0,
                    "scratch": {"timestamp": "20230810101000"},
                    "created_at": "2023-07-03T01:02:09.025856Z",
                    "updated_at": "2025-02-16T00:10:18.774025Z",
                },
                response_only=True,
            ),
        ],
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @extend_schema(
        request=AddOnEventSerializer,
        responses={200: AddOnEventSerializer},
        examples=[
            OpenApiExample(
                "Partial Update Add-On Event Request",
                description="A request to partially update an add-on event.",
                value={
                    "event": 0,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Partial Update Add-On Event Response",
                description=(
                    "A response after successfully partially updating an add-on event."
                ),
                value={
                    "id": 616,
                    "addon": 436,
                    "user": 102112,
                    "parameters": {
                        "site": "https://github.com/duckduckgrayduck/pdf-splitter-add-on/issues",  # pylint:disable=line-too-long
                        "selector": "*",
                    },
                    "event": 0,
                    "scratch": {"timestamp": "20230901090900"},
                    "created_at": "2023-07-03T01:02:09.025856Z",
                    "updated_at": "2025-02-16T00:10:18.774025Z",
                },
                response_only=True,
            ),
        ],
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @lru_cache()
    def get_queryset(self):
        """Only fetch add-on events viewable to this user"""
        queryset = AddOnEvent.objects.get_viewable(self.request.user).order_by("-pk")
        if is_expanded(self.request, "addon"):
            queryset = queryset.select_related("addon")
        return queryset

    def perform_create(self, serializer):
        instance = serializer.save(user=self.request.user)
        if instance.event in [Event.hourly, Event.daily, Event.weekly]:
            instance.dispatch()

    class Filter(django_filters.FilterSet):
        addon = django_filters.NumberFilter(
            field_name="addon",
            lookup_expr="exact",
            help_text="Filter events by a specific add-on ID.",
        )

        class Meta:
            model = AddOnEvent
            fields = ["addon"]

    filterset_class = Filter


@csrf_exempt
def github_webhook(request):
    def verify_signature(request):
        hmac_digest = (
            "sha256="
            + hmac.new(
                key=settings.GITHUB_WEBHOOK_SECRET.encode("utf8"),
                msg=request.body,
                digestmod=hashlib.sha256,
            ).hexdigest()
        )
        return hmac.compare_digest(
            str(request.headers["x-hub-signature-256"]), str(hmac_digest)
        )

    if not verify_signature(request):
        return HttpResponseForbidden()

    data = json.loads(request.body)
    logger.info("[GITHUB WEBHOOK] data %s", json.dumps(data, indent=2))

    acct, _created = GitHubAccount.objects.get_or_create(
        uid=data["sender"]["id"], defaults={"name": data["sender"]["login"]}
    )
    if data.get("action") in ["added", "created"]:
        logger.info("[GITHUB WEBHOOK] %s", data["action"])
        installation, _created = GitHubInstallation.objects.get_or_create(
            iid=data["installation"]["id"],
            defaults={
                "account": acct,
                "name": data["installation"]["account"]["login"],
                "removed": False,
            },
        )
        if data["action"] == "added":
            repos = data["repositories_added"]
        elif data["action"] == "created":
            repos = data["repositories"]
        for repo in repos:
            logger.info("[GITHUB WEBHOOK] added %s", repo["full_name"])
            with transaction.atomic():
                AddOn.objects.update_or_create(
                    repository=repo["full_name"],
                    defaults=dict(
                        github_account=acct,
                        github_installation=installation,
                        removed=False,
                    ),
                )
                transaction.on_commit(
                    lambda r=repo: update_config.delay(r["full_name"])
                )
    elif data.get("action") in ["removed", "deleted"]:
        logger.info("[GITHUB WEBHOOK] %s", data["action"])
        if data["action"] == "removed":
            repos = data["repositories_removed"]
            GitHubInstallation.objects.update_or_create(
                iid=data["installation"]["id"],
                defaults={
                    "acct": acct,
                    "name": data["installation"]["account"]["login"],
                    "removed": True,
                },
            )
        elif data["action"] == "deleted":
            repos = data["repositories"]
        for repo in repos:
            logger.info("[GITHUB WEBHOOK] removed %s", repo["full_name"])
            AddOn.objects.filter(repository=repo["full_name"]).update(removed=True)
    elif data.get("action") == "renamed":
        logger.info("[GITHUB WEBHOOK] %s", data["action"])
        new_name = data["repository"]["full_name"]
        prefix = new_name.split("/", 1)[0]
        old_name = f"{prefix}/" + data["changes"]["repository"]["name"]["from"]
        AddOn.objects.filter(repository=old_name).update(repository=new_name)
        logger.info("[GITHUB WEBHOOK] renamed %s to %s", old_name, new_name)

    return HttpResponse()


@staff_member_required
def dashboard(request):
    timezone.activate("America/New_York")
    context = {"fail_limit": settings.ADDON_DASH_FAIL_LIMIT, "addons": []}
    days = settings.ADDON_DASH_DAYS
    for day in days:
        start = timezone.now() - timedelta(days=day)
        start_filter = Q(runs__created_at__gte=start)
        context["addons"].append(
            {
                "days": day,
                "start": start,
                "addons": AddOn.objects.annotate(
                    run_count=Count("runs", filter=start_filter)
                )
                .annotate(
                    success_count=Count(
                        "runs", filter=Q(runs__status="success") & start_filter
                    ),
                    fail_count=Count(
                        "runs", filter=Q(runs__status="failure") & start_filter
                    ),
                    cancelled_count=Count(
                        "runs",
                        filter=Q(runs__status="cancelled") & start_filter,
                    ),
                    fail_rate=Case(
                        When(run_count=0, then=0),
                        default=((F("fail_count") + F("cancelled_count")) * Value(100))
                        / F("run_count"),
                    ),
                    up_count=Count("runs", filter=Q(runs__rating=1) & start_filter),
                    down_count=Count("runs", filter=Q(runs__rating=-1) & start_filter),
                    up_comments=StringAgg(
                        Concat("runs__comment", Value(" -"), "runs__user__username"),
                        "\n",
                        distinct=True,
                        filter=Q(runs__rating=1) & start_filter,
                    ),
                    down_comments=StringAgg(
                        Concat("runs__comment", Value(" -"), "runs__user__username"),
                        "\n",
                        distinct=True,
                        filter=Q(runs__rating=-1) & start_filter,
                    ),
                    user_count=Count("runs__user", distinct=True, filter=start_filter),
                    user_string=StringAgg(
                        "runs__user__name",
                        "\n",
                        distinct=True,
                        filter=start_filter,
                    ),
                )
                .order_by("-run_count")[: settings.ADDON_DASH_LIMIT],
            }
        )
    return render(request, "addons/dashboard.html", context)


@staff_member_required
def scraper_dashboard(request):
    scraper = get_object_or_404(AddOn, pk=105)
    data = scraper.runs.values("event__parameters__site").annotate(
        success=Count("id", filter=Q(status="success")),
        failure=Count("id", filter=Q(status__in=("failure", "cancelled"))),
    )
    hosts = defaultdict(lambda: {"success": 0, "failure": 0})
    for datum in data:
        url = furl(datum["event__parameters__site"])
        hosts[url.host]["success"] += datum["success"]
        hosts[url.host]["failure"] += datum["failure"]
    context = {"hosts": dict(hosts)}
    return render(request, "addons/scraper.html", context)


class AddOnRunFileServer(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, *args, **kwargs):
        addon_run = get_object_or_404(
            AddOnRun.objects.get_viewable(request.user), uuid=kwargs["uuid"]
        )
        if addon_run.file_name:
            url = storage.presign_url(addon_run.file_path(), "get_object")
        else:
            raise Http404

        if request.META.get("HTTP_ACCEPT", "").startswith("application/json"):
            return JsonResponse({"location": url})
        else:
            return HttpResponseRedirect(url)


class VisualAddOnProxy(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, *args, **kwargs):
        visual_addon = get_object_or_404(
            VisualAddOn.objects.get_viewable(request.user), slug=kwargs["slug"]
        )

        url = visual_addon.url
        if not url.endswith("/"):
            url += "/"
        url += kwargs.get("path", "")

        response = requests.get(url)
        return HttpResponse(
            content=response.content,
            status=response.status_code,
            content_type=response.headers["Content-Type"],
        )
