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
from furl import furl
from rest_flex_fields import FlexFieldsModelViewSet
from rest_flex_fields.utils import is_expanded

# DocumentCloud
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
        premium = django_filters.BooleanFilter(method="premium_filter", label="Premium")
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
    permit_list_expands = ["addon"]
    filter_backends = [filters.OrderingFilter, DjangoFilterBackend]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

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
        event = ModelChoiceFilter(model=AddOnEvent)
        addon = ModelChoiceFilter(model=AddOn)

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

    @lru_cache()
    def get_queryset(self):
        """Only fetch add-on events viewable to this user"""
        queryset = AddOnEvent.objects.get_viewable(self.request.user).order_by("-pk")
        if is_expanded(self.request, "addon"):
            queryset = queryset.select_related("addon")
        return queryset

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    class Filter(django_filters.FilterSet):
        class Meta:
            model = AddOnEvent
            fields = {"addon": ["exact"]}

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
                        "runs", filter=Q(runs__status="cancelled") & start_filter
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
