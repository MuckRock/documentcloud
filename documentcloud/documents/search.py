# Django
from django.conf import settings
from django.urls import reverse

# Standard Library
import logging
import math
import sys

# Third Party
import pysolr

# DocumentCloud
from documentcloud.core.pagination import PageNumberPagination
from documentcloud.organizations.models import Organization
from documentcloud.organizations.serializers import OrganizationSerializer
from documentcloud.users.models import User
from documentcloud.users.serializers import UserSerializer

logger = logging.getLogger(__name__)

FIELD_MAP = {
    "user": "user",
    "organization": "organization",
    "access": "access",
    "status": "status",
    "project": "projects",
    "document": "id",
    "title": "title",
    "source": "source",
    "description": "description",
}
SORT_MAP = {
    "score": "score desc, created_at desc",
    "created_at": "created_at desc",
    "page_count": "page_count desc, created_at desc",
    "title": "title_sort asc, created_at desc",
    "source": "source_sort asc, created_at desc",
}
SOLR = pysolr.Solr(
    settings.SOLR_URL,
    auth=settings.SOLR_AUTH,
    search_handler=settings.SOLR_SEARCH_HANDLER,
    verify=settings.SOLR_VERIFY,
)


def search(user, query_params):
    """
    Given a user and query_params, perform a search for documents in Solr
    `user` is used to restrict access on documents - it may be an anonymous user
    `query_params` allows for text queries, other filters, sorting, and paginating
    """
    # if no text query is given, use "*:*" to search for all documents
    text_query = query_params.get("q", "*:*")
    # remove curly braces to disallow subqueries
    text_query.replace("{", "").replace("}", "")
    field_queries = _field_queries(user, query_params)
    sort = SORT_MAP.get(query_params.get("order"), SORT_MAP["score"])
    rows, start, page = _paginate(query_params)

    kwargs = {"fq": field_queries, "sort": sort, "rows": rows, "start": start}

    try:
        results = SOLR.search(text_query, **kwargs)
    except pysolr.SolrError as exc:
        logger.error(
            "Solr Error: User: %s Query Params: %s Exc: %s",
            user,
            query_params,
            exc,
            exc_info=sys.exc_info(),
        )
        response = {"error": "There has been an error with your search query"}
    else:
        response = _format_response(results, query_params, page, rows)

    if settings.DEBUG:
        response["debug"] = {"text_query": text_query, **kwargs}
    return response


def _field_queries(user, query_params):
    """Field queries restrict the search for a non-text query based on the
    given value for a given field
    """
    field_queries = _access_filter(user)

    # handle generally supported filter fields
    for param, field in FIELD_MAP.items():
        if param in query_params:
            values = " OR ".join(query_params.getlist(param))
            field_queries.append(f"{field}:({values})")

    # handle filtering on user defined data
    data_params = [p for p in query_params if p.startswith("data_")]
    for param in data_params:
        values = query_params.getlist(param)
        if "!" in values:
            field_queries.append(f"!{param}:(*)")
        else:
            values = " OR ".join(query_params.getlist(param))
            field_queries.append(f"{param}:({values})")

    return field_queries


def _access_filter(user):
    """Restrict the user to documents that have access to"""
    if user.is_authenticated:
        organizations = " OR ".join(
            str(o) for o in user.organizations.values_list("pk", flat=True)
        )
        projects = " OR ".join(
            str(p) for p in user.projects.values_list("pk", flat=True)
        )
        access_filter = (
            f"(access:public AND status:(success OR readable))"
            f" OR (user:{user.pk})"
            f" OR (access:organization AND organization:({organizations}))"
        )
        if projects:
            access_filter += f" OR (projects:({projects}))"
        return ["!access:invisible", access_filter]
    else:
        return ["access:public", "status:(success OR readable)"]


def _paginate(query_params):
    """Emulate the Django Rest Framework pagination style"""

    def get_int(field, default, max_value=None):
        """Helper function to convert a parameter to an integer"""
        try:
            value = int(query_params.get(field, default))
            if max_value is not None:
                value = min(value, max_value)
            return value
        except ValueError:
            return default

    rows = get_int(
        PageNumberPagination.page_size_query_param,
        PageNumberPagination.page_size,
        PageNumberPagination.max_page_size,
    )
    page = get_int(PageNumberPagination.page_query_param, 1)
    start = (page - 1) * rows
    return rows, start, page


def _format_response(results, query_params, page, per_page):
    """Emulate the Django Rest Framework response format"""
    base_url = settings.DOCCLOUD_API_URL + reverse("document-search")
    query_params = query_params.copy()

    max_page = math.ceil(results.hits / per_page)
    if page < max_page:
        query_params["page"] = page + 1
        next_url = f"{base_url}?{query_params.urlencode()}"
    else:
        next_url = None

    if page > 1:
        query_params["page"] = page - 1
        previous_url = f"{base_url}?{query_params.urlencode()}"
    else:
        previous_url = None

    expands = query_params.get("expand", "").split(",")
    count = results.hits

    results = _add_asset_url(_format_data(_format_highlights(results)))
    if "user" in expands:
        results = _expand_users(results)
    if "organization" in expands:
        results = _expand_organizations(results)

    response = {
        "count": count,
        "next": next_url,
        "previous": previous_url,
        "results": results,
    }
    return response


def _format_data(results):
    """Collapse the data fields from solr into a single dictionary"""

    def consolidate_data(result):
        data = {
            key[len("data_") :]: values
            for key, values in result.items()
            if key.startswith("data_")
        }
        result = {
            key: values for key, values in result.items() if not key.startswith("data_")
        }
        result["data"] = data
        return result

    return [consolidate_data(r) for r in results]


def _format_highlights(results):
    """Put the highlight data with the corresponding document"""

    return [{**r, "highlights": results.highlighting.get(r["id"])} for r in results]


def _add_asset_url(results):
    for result in results:
        if result["access"] == "public" and result["status"] in ("success", "readable"):
            result["asset_url"] = settings.PUBLIC_ASSET_URL
        else:
            result["asset_url"] = settings.PRIVATE_ASSET_URL
    return results


def _expand_users(results):
    return _expand(results, "user", User.objects.preload_list(), UserSerializer)


def _expand_organizations(results):
    return _expand(
        results, "organization", Organization.objects.all(), OrganizationSerializer
    )


def _expand(results, key, queryset, serializer):
    ids = {r[key] for r in results}
    objs = queryset.filter(pk__in=ids)
    obj_dict = {obj.pk: serializer(obj).data for obj in objs}
    for result in results:
        result[key] = obj_dict[result[key]]
    return results
