# Django
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views import defaults as default_views
from django.views.generic.base import RedirectView
from documentcloud.entities.views import EntityViewSet
from rest_framework import permissions

# Third Party
from rest_framework_nested.routers import NestedDefaultRouter

# DocumentCloud
from documentcloud.addons.views import (
    AddOnEventViewSet,
    AddOnRunFileServer,
    AddOnRunViewSet,
    AddOnViewSet,
    dashboard,
    github_webhook,
)
from documentcloud.core.views import FileServer, account_logout, mailgun
from documentcloud.documents.views import (
    DataViewSet,
    DocumentErrorViewSet,
    DocumentViewSet,
    EntityDateViewSet,
    LegacyEntityViewSet,
    ModificationViewSet,
    NoteViewSet,
    RedactionViewSet,
    SectionViewSet,
)
from documentcloud.drf_bulk.routers import BulkDefaultRouter, BulkRouterMixin
from documentcloud.organizations.views import OrganizationViewSet
from documentcloud.projects.views import (
    CollaborationViewSet,
    ProjectMembershipViewSet,
    ProjectViewSet,
)
from documentcloud.sidekick.routers import SidekickRouter
from documentcloud.sidekick.views import SidekickViewSet
from documentcloud.users.views import MessageView, UserViewSet


class BulkNestedDefaultRouter(BulkRouterMixin, NestedDefaultRouter):
    pass


router = BulkDefaultRouter()
router.register("documents", DocumentViewSet)
router.register("organizations", OrganizationViewSet)
router.register("projects", ProjectViewSet)
router.register("users", UserViewSet)
router.register("addons", AddOnViewSet)
router.register("addon_runs", AddOnRunViewSet)
router.register("addon_events", AddOnEventViewSet)
router.register("entities", EntityViewSet)


documents_router = BulkNestedDefaultRouter(router, "documents", lookup="document")
documents_router.register("notes", NoteViewSet)
documents_router.register("sections", SectionViewSet)
documents_router.register("entities", EntityViewSet)
documents_router.register("legacy_entities", LegacyEntityViewSet)
documents_router.register("dates", EntityDateViewSet)
documents_router.register("errors", DocumentErrorViewSet)
documents_router.register("data", DataViewSet, basename="data")
documents_router.register("redactions", RedactionViewSet, basename="redactions")
documents_router.register(
    "modifications", ModificationViewSet, basename="modifications"
)

projects_router = BulkNestedDefaultRouter(router, "projects", lookup="project")
projects_router.register("documents", ProjectMembershipViewSet)
projects_router.register("users", CollaborationViewSet)

sidekick_router = SidekickRouter(router, "projects", lookup="project")
sidekick_router.register("sidekick", SidekickViewSet)


urlpatterns = [
    path("", RedirectView.as_view(url="/api/"), name="index"),
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/", include(router.urls)),
    path("api/", include(documents_router.urls)),
    path("api/", include(projects_router.urls)),
    path("api/", include(sidekick_router.urls)),
    path("api/", include("documentcloud.oembed.urls")),
    path("api/messages/", MessageView.as_view(), name="message-create"),
    # Social Django
    path("accounts/logout/", account_logout, name="logout"),
    path("accounts/", include("social_django.urls", namespace="social")),
    path("squarelet/", include("squarelet_auth.urls", namespace="squarelet_auth")),
    path(
        "files/documents/<int:pk>/<path:path>", FileServer.as_view(), name="file_server"
    ),
    path(
        "files/addon-runs/<uuid:uuid>/",
        AddOnRunFileServer.as_view(),
        name="addon-run-file",
    ),
    path("github-webhook/", github_webhook, name="github-webhook"),
    path("mailgun/", mailgun, name="mailgun"),
    path("pages/", include("django.contrib.flatpages.urls")),
    path("robots.txt", include("robots.urls")),
    path("addons/dashboard/", dashboard, name="addon-dashboard"),
]

if "debug_toolbar" in settings.INSTALLED_APPS:
    # Third Party
    import debug_toolbar

    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns

if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    urlpatterns += [
        path(
            "400/",
            default_views.bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            default_views.permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            default_views.page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", default_views.server_error),
    ]
