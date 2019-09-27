# Django
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views import defaults as default_views
from rest_framework import permissions

# Third Party
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework_nested import routers

# DocumentCloud
from documentcloud.documents.views import (
    DocumentViewSet,
    EntityDateViewSet,
    EntityViewSet,
    NoteViewSet,
    SectionViewSet,
)
from documentcloud.organizations.views import OrganizationViewSet
from documentcloud.projects.views import (
    CollaborationViewSet,
    ProjectMembershipViewSet,
    ProjectViewSet,
)
from documentcloud.users.views import SocialSessionAuthView, UserViewSet

schema_view = get_schema_view(
    openapi.Info(
        title="DocumentCloud API",
        default_version="v1",
        description="API for Document Cloud",
        terms_of_service="https://www.documentcloud.org/tos/",
        contact=openapi.Contact(email="dylan@documentcloud.org"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

router = routers.DefaultRouter()
router.register("documents", DocumentViewSet)
router.register("organizations", OrganizationViewSet)
router.register("projects", ProjectViewSet)
router.register("users", UserViewSet)

documents_router = routers.NestedDefaultRouter(router, "documents", lookup="document")
documents_router.register("notes", NoteViewSet)
documents_router.register("sections", SectionViewSet)
documents_router.register("entities", EntityViewSet)
documents_router.register("dates", EntityDateViewSet)

projects_router = routers.NestedDefaultRouter(router, "projects", lookup="project")
projects_router.register("documents", ProjectMembershipViewSet)
projects_router.register("users", CollaborationViewSet)


urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path(
        "api/login/social/session/<provider>/",
        SocialSessionAuthView.as_view(),
        name="login_social_session",
    ),
    path("api/", include(router.urls)),
    path("api/", include(documents_router.urls)),
    path("api/", include(projects_router.urls)),
    path(
        "swagger<format>", schema_view.without_ui(cache_timeout=0), name="schema-json"
    ),
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

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
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
