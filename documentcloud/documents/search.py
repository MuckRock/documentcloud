# Django
from django.conf import settings
from django.http.request import QueryDict
from django.urls import reverse

# Standard Library
import math
import re

# Third Party
import pysolr
from luqum.parser import ParseError, parser
from luqum.tree import Boost, Not, Prohibit, Unary
from luqum.utils import LuceneTreeTransformer, LuceneTreeVisitor

# DocumentCloud
from documentcloud.core.pagination import PageNumberPagination
from documentcloud.documents.constants import DATA_KEY_REGEX
from documentcloud.organizations.models import Organization
from documentcloud.organizations.serializers import OrganizationSerializer
from documentcloud.users.models import User
from documentcloud.users.serializers import UserSerializer

FILTER_FIELDS = {
    "id": "id",
    "document": "id",
    "access": "access",
    "status": "status",
    "language": "language",
    "organization": "organization",
    "group": "organization",
    "projects": "projects",
    "project": "projects",
    "slug": "slug",
    "user": "user",
    "account": "user",
    "tag": "data__tag",
    "created_at": "created_at",
    "updated_at": "updated_at",
    "page_count": "page_count",
    "pages": "page_count",
}
DYNAMIC_FILTER_FIELDS = [rf"data_{DATA_KEY_REGEX}"]
ID_FIELDS = ["id", "organization", "projects", "user"]
# XXX switch to DateRange fields for date fields

TEXT_FIELDS = {
    "title": "title",
    "source": "source",
    "description": "description",
    "doctext": "doctext",
    "text": "doctext",
}
DYNAMIC_TEXT_FIELDS = [r"page_no_[0-9]+"]

SORT_MAP = {
    "score": "score desc, created_at desc",
    "created_at": "created_at desc",
    "-created_at": "created_at asc",
    "page_count": "page_count desc, created_at desc",
    "-page_count": "page_count asc, created_at desc",
    "title": "title_sort asc, created_at desc",
    "-title": "title_sort desc, created_at desc",
    "source": "source_sort asc, created_at desc",
    "-source": "source_sort desc, created_at desc",
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
    text_query = query_params.get("q", "")

    text_query, filter_params, sort_order = _parse(text_query, query_params)

    filter_params.update(query_params)
    field_queries = _field_queries(user, filter_params)

    # "sort" or "order" query param takes precedence, then "sort:" filter passed in the
    # query, then fall back to default of score
    sort = SORT_MAP.get(
        query_params.get("sort", query_params.get("order", sort_order)),
        SORT_MAP["score"],
    )
    rows, start, page = _paginate(query_params)

    kwargs = {"fq": field_queries, "sort": sort, "rows": rows, "start": start}

    results = SOLR.search(text_query, **kwargs)
    response = _format_response(results, query_params, page, rows)

    if settings.DEBUG:
        response["debug"] = {"text_query": text_query, **kwargs}
    return response


class BooleanDetector(LuceneTreeVisitor):
    """Walk the tree looking for any AND or OR nodes"""

    def visit_base_operation(self, node, _parents=None):
        return [node.op in ("AND", "OR")]


class RemoveRootError(Exception):
    """An exception signifying to remove the entire parse tree"""


class SlugRemover(LuceneTreeTransformer):
    """Remove the slug in <slug>-<id> formatted valued"""

    def _ignore_slug(self, value):
        """Just take the value past the last dash
        If there is no dash, this will just return the entire value as is
        """
        return value.rsplit("-", 1)[-1]

    def visit_word(self, node, _parents=None):
        node.value = self._ignore_slug(node.value)
        return node

    def visit_phrase(self, node, _parents=None):
        # strip quotes
        value = node.value[1:-1]
        value = self._ignore_slug(value)
        node.value = f'"{value}"'
        return node


class FilterExtractor(LuceneTreeTransformer):
    """Extract all of the applicable search filters from the text query
    to use as field queries
    """

    def __init__(self, *args, **kwargs):
        self.sort_only = kwargs.pop("sort_only", False)
        super().__init__(*args, **kwargs)
        self.filters = QueryDict(mutable=True)
        self.sort = None

    def visit(self, node, parents=None):
        try:
            return super().visit(node, parents)
        except RemoveRootError:
            # if not at root, keep reraising the error until we get to the root,
            # then return None
            if parents is None:
                return None
            else:
                raise

    def visit_search_field(self, node, parents):
        if node.name in FILTER_FIELDS:
            filter_name = FILTER_FIELDS[node.name]
            # update the node name to what it aliases to,
            # so that the alias will hold even if we are in sort only mode
            node.name = filter_name
        elif any(re.match(rf"^{p}$", node.name) for p in DYNAMIC_FILTER_FIELDS):
            filter_name = node.name
        else:
            filter_name = None
        if filter_name and not self.sort_only:
            if filter_name in ID_FIELDS:
                # remove the slug if its an ID field
                value = str(SlugRemover().visit(node.expr))
            else:
                value = str(node.expr)

            if parents and isinstance(parents[-1], (Not, Prohibit)):
                filter_name = f"-{filter_name}"
            self.filters.appendlist(filter_name, value)
            self.prune_parents(parents)
            return None
        elif node.name in ("sort", "order"):
            self.sort = str(node.expr)
            self.prune_parents(parents)
            return None
        else:
            return node

    def prune_parents(self, parents):
        """If we are removing a search node, this allows us to also remove any
        unary parents from the tree
        """
        # only need to worry about Boost and Unary when removing search fields
        # they are the only parents a search field can have which are unary

        if len(parents) > 1 and isinstance(parents[-1], (Boost, Unary)):
            self.replace_node(parents[-1], None, parents[-2])
        elif len(parents) == 1 and isinstance(parents[-1], (Boost, Unary)):
            raise RemoveRootError


def _parse(text_query, query_params):
    """Parse the text query and pull out filters and sorts

    Accepts a text query
    Returns a tuple of (text_query, filters, sort)
        text_query - new text query with filters and sorts removed
        filters - a list of filters to be passed in to solr as field queries
            (`fq` field)
        sort - a string from the SORT_MAP to sort on
    """
    try:
        tree = parser.parse(text_query)
    except (ParseError, TypeError):
        # XXX do auto escape algorithm here
        new_query = text_query
        filters = QueryDict(mutable=True)
        sort = None
    else:
        # check for boolean expressions to determine if we should pull out
        # all filters or only sort filters
        is_boolean = any(BooleanDetector().visit(tree))
        filter_extractor = FilterExtractor(sort_only=is_boolean)
        tree = filter_extractor.visit(tree)

        new_query = str(tree) if tree is not None else ""
        filters = filter_extractor.filters
        sort = filter_extractor.sort

    # pull text queries from the parameters into the text query
    additional_text = _handle_params(query_params, TEXT_FIELDS, DYNAMIC_TEXT_FIELDS)
    if additional_text:
        new_query = "{} {}".format(new_query, " ".join(additional_text))

    # if nothing is left in the query after pulling out filters, default to *:*
    # which matches everything, otherwise convert the parse tree back to a text query
    if not new_query:
        new_query = "*:*"

    return new_query, filters, sort


def _field_queries(user, query_params):
    """Field queries restrict the search for a non-text query based on the
    given value for a given field
    """
    field_queries = _access_filter(user)
    field_queries.extend(
        _handle_params(query_params, FILTER_FIELDS, DYNAMIC_FILTER_FIELDS)
    )

    return field_queries


def _handle_params(query_params, fields, dynamic_fields):
    """Convert query params to a list of Solr field queries"""
    return_list = []
    items = list(fields.items())
    # add negated version of all fields
    items = items + [(f"-{p}", f"-{f}") for p, f in items]
    for param, field in items:
        if param in query_params:
            # joining with whitespace will default to OR
            values = " ".join(query_params.getlist(param))
            return_list.append(f"{field}:({values})")

    for pattern in dynamic_fields:
        # allow for negated dynamic fields
        dynamic_params = [p for p in query_params if re.match(fr"^-?{pattern}$", p)]
        for param in dynamic_params:
            values = " ".join(query_params.getlist(param))
            return_list.append(f"{param}:({values})")

    return return_list


def _access_filter(user):
    """Restrict the user to documents that have access to"""
    if user.is_authenticated:
        organizations = " ".join(
            str(o) for o in user.organizations.values_list("pk", flat=True)
        )
        projects = " ".join(str(p) for p in user.projects.values_list("pk", flat=True))
        access_filter = (
            f"filter(access:public AND status:(success readable))"
            f" OR (user:{user.pk})"
            f" OR (access:organization AND organization:({organizations}))"
        )
        if projects:
            access_filter += f" OR (projects_edit_access:({projects}))"
        return ["!access:invisible", access_filter]
    else:
        return ["access:public AND status:(success readable)"]


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
    from documentcloud.documents.tasks import solr_index

    for result in results:
        # access and status should always be available, re-index if they are not
        if "access" not in result or "status" not in result:
            solr_index.delay(result["id"])
            result["asset_url"] = settings.PRIVATE_ASSET_URL
        elif result["access"] == "public" and result["status"] in (
            "success",
            "readable",
        ):
            result["asset_url"] = settings.PUBLIC_ASSET_URL
        else:
            result["asset_url"] = settings.PRIVATE_ASSET_URL
    return results


def _expand_users(results):
    return _expand(results, "user", User.objects.preload(), UserSerializer)


def _expand_organizations(results):
    return _expand(
        results, "organization", Organization.objects.all(), OrganizationSerializer
    )


def _expand(results, key, queryset, serializer):
    from documentcloud.documents.tasks import solr_index

    ids = {r[key] for r in results if key in r}
    objs = queryset.filter(pk__in=ids)
    obj_dict = {obj.pk: serializer(obj).data for obj in objs}
    for result in results:
        # user and organization should always be available, re-index if they are not
        if key not in result:
            solr_index.delay(result["id"])
        else:
            result[key] = obj_dict.get(result[key])
    return results
