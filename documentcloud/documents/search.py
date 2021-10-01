# Django
from django.conf import settings
from django.http.request import QueryDict

# Standard Library
import math
import re
from datetime import datetime

# Third Party
import pysolr
from luqum.parser import ParseError, parser
from luqum.tree import Boost, Not, Prohibit, Unary
from luqum.utils import LuceneTreeTransformer, LuceneTreeVisitor

# DocumentCloud
from documentcloud.core.pagination import PageNumberPagination
from documentcloud.documents.constants import DATA_KEY_REGEX
from documentcloud.documents.models import Document
from documentcloud.documents.search_escape import escape
from documentcloud.organizations.models import Organization
from documentcloud.organizations.serializers import OrganizationSerializer
from documentcloud.projects.choices import CollaboratorAccess
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
NUMERIC_FIELDS = ID_FIELDS + ["page_count"]
DATE_FIELDS = ["created_at", "updated_at"]

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
    timeout=settings.SOLR_TIMEOUT,
)


def search(user, query_params):
    """
    Given a user and query_params, perform a search for documents in Solr
    `user` is used to restrict access on documents - it may be an anonymous user
    `query_params` allows for text queries, other filters, sorting, and paginating
    """
    text_query = query_params.get("q", "")

    text_query, filter_params, sort_order, escaped, use_hl = _parse(
        text_query, query_params, user
    )
    text_query = _add_note_query(text_query, user)

    filter_params.update(query_params)
    filter_queries = _filter_queries(user, filter_params)

    # "sort" or "order" query param takes precedence, then "sort:" filter passed in the
    # query, then fall back to default of score
    sort = SORT_MAP.get(
        query_params.get("sort", query_params.get("order", sort_order)),
        SORT_MAP["score"],
    )
    rows, start, page = _paginate(query_params, user)

    # allow explicit enabling of highlighting
    if query_params.get("hl", "").lower() == "true":
        use_hl = True

    kwargs = {
        "fq": filter_queries,
        "sort": sort,
        "rows": rows,
        "start": start,
        "uf": "* _query_ -edit_access",
        "hl": "on" if settings.SOLR_USE_HL and use_hl else "off",
        "hl.requireFieldMatch": settings.SOLR_HL_REQUIRE_FIELD_MATCH,
        "hl.highlightMultiTerm": settings.SOLR_HL_MULTI_TERM,
    }
    # these are for calculating edit access
    if user.is_authenticated:
        organizations = user.organizations.all()
        projects = user.projects.filter(
            collaboration__access__in=(
                CollaboratorAccess.admin,
                CollaboratorAccess.edit,
            )
        )
        kwargs.update(
            {
                "qq_user": user.pk,
                "qq_organizations": ",".join(str(o.pk) for o in organizations),
                "qq_projects": ",".join(str(p.pk) for p in projects),
            }
        )

    results = SOLR.search(text_query, **kwargs)
    response = _format_response(results, query_params, user, page, rows, escaped)

    if settings.DEBUG or user.is_staff:
        response["debug"] = {"text_query": text_query, "qtime": results.qtime, **kwargs}
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


class Validator(LuceneTreeVisitor):
    """Validate word and phrase nodes"""

    def visit_word(self, node, _parents=None):
        return [self._validate(node.value)]

    def visit_phrase(self, node, _parents=None):
        # remove quotes
        return [self._validate(node.value[1:-1])]


class NumberValidator(Validator):
    """Validate nodes are numbers"""

    def _validate(self, value):
        return value.isdecimal()


class DateValidator(Validator):
    """Validate nodes are numbers"""

    datetime_pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?P<micros>\.\d+)?Z"
    # https://github.com/apache/lucene-solr/blob/
    # 1d85cd783863f75cea133fb9c452302214165a4d/solr/core/src/java/org/apache/solr/
    # util/DateMathParser.java#L153
    unit_pattern = r"((YEAR|MONTH|DAY|HOUR|MINUTE|SECOND|MILLI|MILLISECOND)S?|DATE)"
    regex = re.compile(
        rf"""
        ^
        (?P<date>NOW|{datetime_pattern}) # the base date can be NOW or a timestamp
        (/{unit_pattern})?               # this may be rounded to the nearest unit
        (
            (\+|-)\d+{unit_pattern}      # you may add or subtract a number of units
            (/{unit_pattern})?           # optionally rounded to the nearest unit
        )*                               # you may have zero or more of these
        $
        """,
        re.VERBOSE,
    )

    def visit_word(self, node, _parents=None):
        """Always escape dates if they are unquoted"""
        valid = super().visit_word(node)
        if valid[0]:
            node.value = node.value.replace(":", "\\:")
        return valid

    def _validate(self, value):
        if value == "*":
            return True

        match = self.regex.match(value)
        if not match:
            return False

        if match.group("date") == "NOW":
            return True

        try:
            if match.group("micros"):
                datetime.strptime(match.group("date"), "%Y-%m-%dT%H:%M:%S.%fZ")
            else:
                datetime.strptime(match.group("date"), "%Y-%m-%dT%H:%M:%SZ")
            return True
        except ValueError:
            return False


class SearchFieldDetector(LuceneTreeVisitor):
    """Validate that there are no nested search fields"""

    def visit_search_field(self, _node, _parents=None):
        return [True]


class FuzzyDetector(LuceneTreeVisitor):
    """Validate that there are no nested search fields"""

    def visit_fuzzy(self, _node, _parents=None):
        return [True]


class FilterExtractor(LuceneTreeTransformer):
    """Extract all of the applicable search filters from the text query
    to use as field queries
    """

    def __init__(self, *args, **kwargs):
        self.sort_only = kwargs.pop("sort_only", False)
        super().__init__(*args, **kwargs)
        self.filters = QueryDict(mutable=True)
        self.sort = None
        self.use_hl = False

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
        # pylint: disable=too-many-return-statements
        # substitute any aliases
        if node.name in FILTER_FIELDS:
            filter_name = FILTER_FIELDS[node.name]
            # update the node name to what it aliases to,
            # so that the alias will hold even if we are in sort only mode
            node.name = filter_name
        elif any(re.match(rf"^{p}$", node.name) for p in DYNAMIC_FILTER_FIELDS):
            filter_name = node.name
        else:
            filter_name = None

        # remove slugs from ID fields
        if filter_name in ID_FIELDS:
            # remove the slug if its an ID field
            node.expr = SlugRemover().visit(node.expr)

        # extract the filters
        if filter_name and not self.sort_only:

            # validate fields and do not add to filters if they fail
            if filter_name in NUMERIC_FIELDS and not all(
                NumberValidator().visit(node.expr)
            ):
                return node

            if filter_name in DATE_FIELDS and not all(DateValidator().visit(node.expr)):
                return node

            # no filters may have nested search fields
            if any(SearchFieldDetector().visit(node.expr)):
                return node

            if parents and isinstance(parents[-1], (Not, Prohibit)):
                filter_name = f"-{filter_name}"
            self.filters.appendlist(filter_name, str(node.expr))
            self.prune_parents(parents)
            return None
        elif node.name in ("sort", "order"):
            self.sort = str(node.expr)
            self.prune_parents(parents)
            return None
        elif node.name == "hl":
            self.use_hl = str(node.expr).lower() == "true"
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


class AnonymousTransformer(LuceneTreeTransformer):
    """Remove computational expesnive searches from anonymous queries"""

    def visit_fuzzy(self, node, _parents):
        """Remove fuzzy searches"""
        return node.term

    def visit_term(self, node, _parents):
        """Escape terms which contain wildcards"""
        if node.has_wildcard():
            node.value = escape(node.value)
        return node


def _parse(text_query, query_params, user):
    """Parse the text query and pull out filters and sorts

    Accepts a text query
    Returns a tuple of (text_query, filters, sort)
        text_query - new text query with filters and sorts removed
        filters - a list of filters to be passed in to solr as field queries
            (`fq` field)
        sort - a string from the SORT_MAP to sort on
    """
    if text_query.strip():
        try:
            tree = parser.parse(text_query)
            escaped = False
        except (ParseError, TypeError):
            tree = parser.parse(escape(text_query))
            escaped = True

        # check for boolean expressions to determine if we should pull out
        # all filters or only sort filters
        is_boolean = any(BooleanDetector().visit(tree))
        # detect fuzzy searches to disable highlighting
        is_fuzzy = any(FuzzyDetector().visit(tree))
        filter_extractor = FilterExtractor(sort_only=is_boolean)
        tree = filter_extractor.visit(tree)

        if not user.is_authenticated:
            tree = AnonymousTransformer().visit(tree)

        new_query = str(tree) if tree is not None else ""
        filters = filter_extractor.filters
        sort = filter_extractor.sort
        # only use highilighting for queries with no fuzzy searches and
        # which do not explicitly turn it off
        use_hl = not is_fuzzy and filter_extractor.use_hl
    else:
        # special case for empty query
        new_query = ""
        filters = QueryDict(mutable=True)
        sort = None
        escaped = False
        use_hl = False

    # pull text queries from the parameters into the text query
    additional_text = _handle_params(query_params, TEXT_FIELDS, DYNAMIC_TEXT_FIELDS)
    if additional_text:
        new_query = "{} {}".format(new_query, " ".join(additional_text))

    # if nothing is left in the query after pulling out filters, default to *:*
    # which matches everything, otherwise convert the parse tree back to a text query
    if not new_query:
        new_query = "*:*"

    return new_query, filters, sort, escaped, use_hl


def _filter_queries(user, query_params):
    """Field queries restrict the search for a non-text query based on the
    given value for a given field
    """
    filter_queries = _access_filter(user)
    filter_queries.extend(
        _handle_params(query_params, FILTER_FIELDS, DYNAMIC_FILTER_FIELDS)
    )

    return filter_queries


def _handle_params(query_params, fields, dynamic_fields):
    """Convert query params to a list of Solr field queries"""
    return_list = []
    items = list(fields.items())
    # add negated version of all fields
    items = items + [(f"-{p}", f"-{f}") for p, f in items]
    for param, field in items:
        if param in query_params:
            # pylint: disable=protected-access
            # joining with whitespace will default to OR
            values = query_params.getlist(param)
            if field in NUMERIC_FIELDS:
                values = [v for v in values if NumberValidator()._validate(v)]
            if field in DATE_FIELDS:
                # validate date fields and escape colons
                values = [
                    v.replace(":", "\\:")
                    for v in values
                    if DateValidator()._validate(v)
                ]
            values = " ".join(values)
            if values:
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
        return ["filter(access:public AND status:(success readable))"]


def _paginate(query_params, user):
    """Emulate the Django Rest Framework pagination style"""

    def get_int(field, default, max_value=None, min_value=None):
        """Helper function to convert a parameter to an integer"""
        try:
            value = int(query_params.get(field, default))
            if max_value is not None:
                value = min(value, max_value)
            if min_value is not None:
                value = max(value, min_value)
            return value
        except ValueError:
            return default

    if user.is_authenticated:
        max_value = PageNumberPagination.max_page_size
    else:
        max_value = settings.SOLR_ANON_MAX_ROWS

    rows = get_int(
        PageNumberPagination.page_size_query_param,
        PageNumberPagination.page_size,
        max_value=max_value,
    )
    page = get_int(PageNumberPagination.page_query_param, 1, min_value=1)
    start = (page - 1) * rows
    return rows, start, page


def _format_response(results, query_params, user, page, per_page, escaped):
    """Emulate the Django Rest Framework response format"""
    base_url = f"{settings.DOCCLOUD_API_URL}/api/documents/search/"
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
        "escaped": escaped,
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


def _add_note_query(text_query, user):
    organizations = " ".join(str(o.pk) for o in user.organizations.all())
    projects = " ".join(
        str(p.pk)
        for p in user.projects.filter(
            collaboration__access__in=(
                CollaboratorAccess.admin,
                CollaboratorAccess.edit,
            )
        )
    )
    # XXX test this!
    return (
        # the original query to search for in documents
        f"({text_query}) "
        # search through notes which are public or that you own
        # on all documents you can view
        f'_query_:"{{!parent which=type:document score=total}}'
        f"+type:note +(access:public OR user:{user.pk}) "
        f'+(title:({text_query}) description:({text_query}))" '
        # search through notes which are organization access
        # on all documents you can edit
        f'_query_:"+('
        f"((user:{user.pk} OR project_edit_access:({projects})) "
        f"AND access:(private organization)) "
        f"OR (access:(public organization) AND organizations:({organizations})) "
        f"{{!parent which=type:document score=total}}"
        f"+type:note +(access:organization) "
        f'(title:({text_query}) description:({text_query}))"'
    )
