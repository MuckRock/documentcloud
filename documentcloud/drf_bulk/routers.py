# Django
from rest_framework.routers import DefaultRouter

# Standard Library
import copy


class BulkRouterMixin:
    routes = copy.deepcopy(DefaultRouter.routes)
    routes[0].mapping.update(
        {"put": "bulk_update", "patch": "bulk_partial_update", "delete": "bulk_destroy"}
    )


class BulkDefaultRouter(BulkRouterMixin, DefaultRouter):
    pass
