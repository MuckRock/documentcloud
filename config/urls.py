# Django
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views import defaults as default_views
from rest_framework import permissions, routers

# Third Party
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

# DocumentCloud
from documentcloud.documents.views import DocumentViewSet
from documentcloud.organizations.views import OrganizationViewSet
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
router.register("users", UserViewSet)
router.register("organizations", OrganizationViewSet)

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/", include(router.urls)),
    # JWT
    path("api/login/", include("rest_social_auth.urls_jwt_pair")),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Swagger
    path(
        "swagger<format>", schema_view.without_ui(cache_timeout=0), name="schema-json"
    ),
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path("accounts/", include("social_django.urls", namespace="social")),
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
