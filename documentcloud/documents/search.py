# Django
from django.conf import settings

# Third Party
import pysolr

# XXX paginate
# XXX text query per field
# XXX data

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


def search(user, query_params):
    query_field, text_query = _text_queries(query_params)
    field_queries = _field_queries(user, query_params)
    sort = SORT_MAP.get(query_params.get("order"), SORT_MAP["score"])

    results = SOLR.search(text_query, qf=query_field, fq=field_queries, sort=sort)

    response = _format_response(results)
    if settings.DEBUG:
        response["debug"] = {
            "text_query": text_query,
            "qf": query_field,
            "fq": field_queries,
            "sort": sort,
        }
    return response


def _field_queries(user, query_params):
    field_queries = [_access_filter(user)]

    for param, field in FIELD_MAP.items():
        if param in query_params:
            values = " OR ".join(query_params.getlist(param))
            field_queries.append(f"{field}:({values})")
    return field_queries


def _text_queries(query_params):
    text_queries = {
        solr_field: query_params[query_field]
        for query_field, solr_field in TEXT_MAP.items()
        if query_field in query_params
    }
    if text_queries:
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
        projects = " OR ".join(
            str(p) for p in user.projects.values_list("pk", flat=True)
        )
        organizations = " OR ".join(
            str(o) for o in user.organizations.values_list("pk", flat=True)
        )
        return (
            f"(access:public AND status:(success OR readable))"
            f"OR (user:{user.pk})"
            f"OR (projects:{projects})"
            f"OR (access:organization AND organization:({organizations})"
        )
    else:
        return "access:public AND status:(success OR readable)"


def _format_response(results):
    response = {
        "count": results.hits,
        "next": None,
        "previous": None,
        "results": results,
    }
    return response
