# Django
from django.conf import settings

# Standard Library
import math

# Third Party
import pysolr

# DocumentCloud
from documentcloud.core.pagination import PageNumberPagination

FIELD_MAP = {
    "user": "user",
    "organization": "organization",
    "access": "access",
    "status": "status",
    "project": "projects",
    "document": "id",
}
TEXT_MAP = {
    "q": None,
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
    settings.SOLR_URL, auth=settings.SOLR_AUTH, search_handler="/mainsearch"
)


def search(user, query_params, base_url):
    query_field, text_query = _text_queries(query_params)
    field_queries = _field_queries(user, query_params)
    sort = SORT_MAP.get(query_params.get("order"), SORT_MAP["score"])
    rows, start, page = _paginate(query_params)

    kwargs = {"fq": field_queries, "sort": sort, "rows": rows, "start": start}
    if query_field is not None:
        kwargs["qf"] = query_field

    try:
        results = SOLR.search(text_query, **kwargs)
    except pysolr.SolrError as exc:
        response = {"error": str(exc)}
    else:
        response = _format_response(results, query_params, base_url, page, rows)

    if settings.DEBUG:
        response["debug"] = {"text_query": text_query, **kwargs}
    return response


def _field_queries(user, query_params):
    field_queries = [_access_filter(user)]

    for param, field in FIELD_MAP.items():
        if param in query_params:
            values = " OR ".join(query_params.getlist(param))
            field_queries.append(f"{field}:({values})")

    data_params = [p for p in query_params if p.startswith("data_")]
    for param in data_params:
        values = query_params.getlist(param)
        if "!" in values:
            field_queries.append(f"!{param}:(*)")
        else:
            values = " OR ".join(query_params.getlist(param))
            field_queries.append(f"{param}:({values})")

    return field_queries


def _text_queries(query_params):
    text_queries = {
        solr_field: query_params[query_field]
        for query_field, solr_field in TEXT_MAP.items()
        if query_field in query_params
    }
    if not text_queries:
        return None, "*:*"
    elif len(text_queries) == 1:
        return list(text_queries.items())[0]
    else:
        # multiple text queries, construct using advanced solr syntax
        query_text = " AND ".join(
            '_query_:"{{!edismax {qf}}}{text}"'.format(
                qf=f"qf='{qf}'" if qf else "", text=" ".join(text)
            )
            for qf, text in text_queries.items()
        )
        return None, query_text


def _access_filter(user):
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
            access_filter += f" OR (projects:{projects})"
        return access_filter
    else:
        return "access:public AND status:(success OR readable)"


def _paginate(query_params):
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


def _format_response(results, query_params, base_url, page, per_page):
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

    response = {
        "count": results.hits,
        "next": next_url,
        "previous": previous_url,
        "results": _format_data(results),
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
