# Django
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.db.models.expressions import Exists, OuterRef, Value
from django.http.response import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# Standard Library
import hashlib
import hmac
import json
import logging
from functools import lru_cache

# Third Party
from django_filters import rest_framework as django_filters
from rest_flex_fields import FlexFieldsModelViewSet
from rest_flex_fields.utils import is_expanded

# DocumentCloud
from documentcloud.addons.models import (
    AddOn,
    AddOnEvent,
    AddOnRun,
    GitHubAccount,
    GitHubInstallation,
)
from documentcloud.addons.serializers import (
    AddOnEventSerializer,
    AddOnRunSerializer,
    AddOnSerializer,
)
from documentcloud.addons.tasks import dispatch, update_config

logger = logging.getLogger(__name__)


class AddOnViewSet(viewsets.ModelViewSet):
    serializer_class = AddOnSerializer
    queryset = AddOn.objects.none()

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
        active = django_filters.BooleanFilter(field_name="active", label="Active")
        query = django_filters.CharFilter(method="query_filter", label="Query")

        def query_filter(self, queryset, name, value):
            # pylint: disable=unused-argument
            return queryset.filter(
                Q(name__icontains=value) | Q(parameters__description__icontains=value)
            )

        class Meta:
            model = AddOn
            fields = []

    filterset_class = Filter


class AddOnRunViewSet(FlexFieldsModelViewSet):
    serializer_class = AddOnRunSerializer
    queryset = AddOnRun.objects.none()
    lookup_field = "uuid"
    permit_list_expands = ["addon"]

    @lru_cache()
    def get_queryset(self):
        """Only fetch add-on runs viewable to this user"""
        queryset = AddOnRun.objects.get_viewable(self.request.user).order_by("-pk")
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

    class Filter(django_filters.FilterSet):
        class Meta:
            model = AddOnRun
            fields = {"dismissed": ["exact"]}

    filterset_class = Filter


class AddOnEventViewSet(FlexFieldsModelViewSet):
    serializer_class = AddOnEventSerializer
    queryset = AddOnEvent.objects.none()
    permit_list_expands = ["addon"]

    @lru_cache()
    def get_queryset(self):
        """Only fetch add-on events viewable to this user"""
        queryset = AddOnEvent.objects.get_viewable(self.request.user).order_by("-pk")
        if is_expanded(self.request, "addon"):
            queryset = queryset.select_related("addon")
        return queryset


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
