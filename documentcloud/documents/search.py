# Django
from django.conf import settings
from django.http.request import QueryDict

# Standard Library
import math
import re
from collections import defaultdict
from datetime import datetime

# Third Party
import pysolr
from luqum.parser import ParseError, parser
from luqum.tree import BaseOperation, Boost, Group, Not, Prohibit, Range, Unary, Word
from luqum.utils import LuceneTreeTransformer, LuceneTreeVisitor

# DocumentCloud
from documentcloud.core.pagination import CursorPagination, PageNumberPagination
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
    "noindex": "noindex",
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
    "score": "score desc, created_at desc, id desc",
    "created_at": "created_at desc, id desc",
    "-created_at": "created_at asc, id desc",
    "page_count": "page_count desc, id desc",
    "-page_count": "page_count asc, id desc",
    "title": "title_sort asc, id desc",
    "-title": "title_sort desc, id desc",
    "source": "source_sort asc, id desc",
    "-source": "source_sort desc, id desc",
    "id": "id asc",
    "-id": "id desc",
}
SOLR = pysolr.Solr(
    settings.SOLR_URL,
    auth=settings.SOLR_AUTH,
    search_handler=settings.SOLR_SEARCH_HANDLER,
    verify=settings.SOLR_VERIFY,
    timeout=settings.SOLR_TIMEOUT,
)
SOLR_NOTES = pysolr.Solr(
    settings.SOLR_NOTES_URL,
    auth=settings.SOLR_AUTH,
    verify=settings.SOLR_VERIFY,
    timeout=settings.SOLR_TIMEOUT,
)


def search(user, query_params):
    """
    Given a user and query_params, perform a search for documents in Solr
    `user` is used to restrict access on documents - it may be an anonymous user
    `query_params` allows for text queries, other filters, sorting, and paginating
    """
    # pylint: disable=too-many-locals
    text_query = query_params.get("q", "")

    text_query, filter_params, sort_order, escaped, use_hl = _parse(
        text_query, query_params, user
    )

    filter_params.update(query_params)
    filter_queries = _filter_queries(user, filter_params)

    # "sort" or "order" query param takes precedence, then "sort:" filter passed in the
    # query, then fall back to default of score
    sort = SORT_MAP.get(
        query_params.get("sort", query_params.get("order", sort_order)),
        SORT_MAP["score"],
    )
    page_query_data, page_response_data = _paginate(query_params, user)

    # allow explicit enabling of highlighting
    if query_params.get("hl", "").lower() == "true" and settings.SOLR_USE_HL:
        use_hl = True

    kwargs = {
        "fq": filter_queries,
        "sort": sort,
        "hl": "on" if use_hl else "off",
        "hl.highlightMultiTerm": settings.SOLR_HL_MULTI_TERM,
        **page_query_data,
    }
    if (
        settings.SOLR_QUERY_NOTES
        and user.is_authenticated
        and user.feature_level >= 1
        and text_query != "*:*"
    ):
        # turn note queries on for all pro users
        # *:* returns all documents, do not enable note queries
        original_text_query = text_query
        text_query = _add_note_query(text_query, user)
        kwargs["uf"] = "* _query_ -projects_edit_access"
        query_notes = True
    else:
        query_notes = False

    # these are for calculating edit access
    if user.is_authenticated and not settings.SOLR_ADD_EDIT_ACCESS:
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
                "notes.qq_user": user.pk,
                "qq_organizations": ",".join(str(o.pk) for o in organizations),
                "qq_projects": ",".join(str(p.pk) for p in projects),
            }
        )

    results = SOLR.search(text_query, **kwargs)
    response = _format_response(
        results, query_params, user, escaped, page_response_data
    )
    if use_hl and query_notes:
        response = _highlight_notes(response, original_text_query)

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
        return value.isdecimal() or value == "*"


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
        # pylint: disable=too-many-return-statements, too-many-branches
        # substitute any aliases
        filter_name = None
        if node.name in FILTER_FIELDS:
            filter_name = FILTER_FIELDS[node.name]
            # update the node name to what it aliases to,
            # so that the alias will hold even if we are in sort only mode
            node.name = filter_name
        elif node.name in TEXT_FIELDS:
            text_name = TEXT_FIELDS[node.name]
            # update the node name to what it aliases to,
            # so that the alias will hold even if we are in sort only mode
            node.name = text_name
        elif any(re.match(rf"^{p}$", node.name) for p in DYNAMIC_FILTER_FIELDS):
            filter_name = node.name

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
        elif node.name == "_query_":
            # remove _query_ for security purposes
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


class NoteExtractor(LuceneTreeTransformer):
    """Extract all search fields (even text ones) from a query, to leave a text
    query that is suitable for searching notes
    """

    def visit(self, node, parents=None):
        new_node = super().visit(node, parents)
        if (
            isinstance(new_node, (Group, BaseOperation, Unary))
            and not any(node.children)
            and parents
        ):
            self.replace_node(new_node, None, parents[-1])
            return None
        return new_node

    def visit_search_field(self, _node, _parents):
        return None


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
        # pylint: disable=consider-using-f-string
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


def _validate_range(value, validator):
    """Validate using the validator as well as ensuring the top level node
    is either a word or range
    """
    node = parser.parse(value)
    return all(validator.visit(node)) and isinstance(node, (Word, Range))


def _handle_params(query_params, fields, dynamic_fields):
    """Convert query params to a list of Solr field queries"""
    return_list = []
    items = list(fields.items())
    # add negated version of all fields
    items = items + [(f"-{p}", f"-{f}") for p, f in items]
    for param, field in items:
        if param in query_params:
            # joining with whitespace will default to OR
            values = query_params.getlist(param)
            if field in NUMERIC_FIELDS:
                values = [v for v in values if _validate_range(v, NumberValidator())]
            if field in DATE_FIELDS:
                # validate date fields and escape colons
                values = [
                    v.replace(":", "\\:")
                    for v in values
                    if _validate_range(v, DateValidator())
                ]
            values = " ".join(values)
            if values:
                return_list.append(f"{field}:({values})")

    for pattern in dynamic_fields:
        # allow for negated dynamic fields
        dynamic_params = [p for p in query_params if re.match(rf"^-?{pattern}$", p)]
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
        return ["filter(access:public AND status:(success readable) AND !noindex:true)"]


def _paginate(query_params, user):  # pylint: disable=inconsistent-return-statements
    """Emulate the Django Rest Framework pagination style"""
    version = query_params.get("version", settings.REST_FRAMEWORK["DEFAULT_VERSION"])

    if version not in ["1.0", "2.0"]:
        version = settings.REST_FRAMEWORK["DEFAULT_VERSION"]

    if version == "1.0":
        return _paginate_page(query_params, user)
    elif version == "2.0":
        return _paginate_cursor(query_params, user)


def _get_int(query_params, field, default, max_value=None, min_value=None):
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


def _paginate_page(query_params, user):
    """Emulate the Django Rest Framework page number pagination style"""

    if user.is_authenticated:
        max_page_size = PageNumberPagination.max_page_size
        max_page = PageNumberPagination.auth_page_limit
    else:
        max_page_size = settings.SOLR_ANON_MAX_ROWS
        max_page = PageNumberPagination.anon_page_limit

    rows = _get_int(
        query_params,
        PageNumberPagination.page_size_query_param,
        PageNumberPagination.page_size,
        max_value=max_page_size,
    )
    page = _get_int(query_params, PageNumberPagination.page_query_param, 1, min_value=1)
    if page > max_page:
        raise ValueError(
            f"The selected `page` value of {page} is over the limit of {max_page}"
        )
    start = (page - 1) * rows
    return {"rows": rows, "start": start}, {"page": page, "rows": rows}


def _paginate_cursor(query_params, user):
    """Emulate the Django Rest Framework cursor pagination style"""

    if user.is_authenticated:
        max_page_size = CursorPagination.max_page_size
    else:
        max_page_size = settings.SOLR_ANON_MAX_ROWS

    cursor = query_params.get("cursor", "*")

    rows = _get_int(
        query_params,
        CursorPagination.page_size_query_param,
        CursorPagination.page_size,
        max_value=max_page_size,
    )
    return {"rows": rows, "cursorMark": cursor}, {}


def _format_response(results, query_params, user, escaped, page_data):
    """Emulate the Django Rest Framework response format"""
    base_url = f"{settings.DOCCLOUD_API_URL}/api/documents/search/"
    query_params = query_params.copy()

    if "page" in page_data:
        page = page_data["page"]
        per_page = page_data["rows"]
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
    else:
        if query_params.get("cursor", "*") == results.nextCursorMark:
            next_url = None
        else:
            query_params["cursor"] = results.nextCursorMark
            next_url = f"{base_url}?{query_params.urlencode()}"
        previous_url = None

    expands = query_params.get("expand", "").split(",")
    count = results.hits

    results = _add_canonical_url(
        _add_asset_url(_format_notes(_format_data(_format_highlights(results))))
    )
    if settings.SOLR_ADD_EDIT_ACCESS:
        results = _add_edit_access(user, results)
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

    return [
        {**r, "highlights": results.highlighting.get(r["id"])} for r in results.docs
    ]


def _format_notes(results):
    """Put note data into the proper format"""

    def format_note(result):
        """Notes are in the `docs` key as returned from Solr
        We merge in the Org notes only if the user has edit access to this document
        """
        if settings.SOLR_ADD_NOTES:
            result["notes"] = result["notes"]["docs"]
            if result["edit_access"]:
                notes = result["notes"]
                org_notes = result["org_notes"]["docs"]
                # merge two lists of sorted notes, removing duplicates
                result["notes"] = []
                while notes or org_notes:
                    # if either list runs out, just add the rest of the other list
                    if notes and not org_notes:
                        result["notes"].extend(notes)
                        notes.clear()
                    elif not notes and org_notes:
                        result["notes"].extend(org_notes)
                        org_notes.clear()
                    # if they are the same, merge them
                    elif notes[0]["id"] == org_notes[0]["id"]:
                        result["notes"].append(notes.pop(0))
                        org_notes.pop(0)
                    # otherwise take the note with the lower page number and append
                    # it next
                    elif notes[0]["page_number"] <= org_notes[0]["page_number"]:
                        result["notes"].append(notes.pop(0))
                    else:
                        result["notes"].append(org_notes.pop(0))

            # remove org_notes from the document
            result.pop("org_notes")
        else:
            result.pop("notes", None)
            result.pop("org_notes", None)

        return result

    return [format_note(r) for r in results]


def _highlight_notes(response, text_query):
    """Do a second query to highlight notes if necessary"""
    notes = [n for d in response["results"] for n in d["notes"]]
    note_ids = [n["id"] for n in notes]
    if not note_ids:
        return response
    parents = {n["id"]: d["id"] for d in response["results"] for n in d["notes"]}
    fq_ = [f"id:({' '.join(note_ids)})"]

    note_query = _extract_note_query(text_query)
    if note_query is None:
        return response
    query = f"title:{note_query} description:{note_query}"

    kwargs = {
        "fq": fq_,
        "rows": 50,
        "start": 0,
        "hl": "on",
        "hl.fl": "title description",
    }

    # dict[doc id] -> (dic[note id] -> (dic[field] -> highlight))
    note_highlights = defaultdict(lambda: defaultdict(dict))
    while True:
        results = SOLR_NOTES.search(query, **kwargs)
        for id_, highlight in results.highlighting.items():
            note_highlights[parents[id_]][id_] = highlight
        if results.hits > kwargs["rows"] + kwargs["start"]:
            kwargs["start"] += kwargs["rows"]
        else:
            break
    for doc in response["results"]:
        doc["note_highlights"] = note_highlights.get(doc["id"], {})
    return response


def _add_canonical_url(results):

    for result in results:
        result[
            "canonical_url"
        ] = f"{settings.DOCCLOUD_URL}/documents/{result['id']}-{result.get('slug', '')}"
    return results


def _add_asset_url(results):
    # DocumentCloud
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


def _add_edit_access(user, results):
    """Add edit_access to results"""
    ids = [r["id"] for r in results]
    editable_documents = [
        str(id_)
        for id_ in Document.objects.get_editable(user)
        .filter(id__in=ids)
        .values_list("id", flat=True)
    ]
    for result in results:
        # access and status should always be available, re-index if they are not
        result["edit_access"] = result["id"] in editable_documents

    return results


def _expand_users(results):
    return _expand(results, "user", User.objects.preload(), UserSerializer)


def _expand_organizations(results):
    return _expand(
        results, "organization", Organization.objects.all(), OrganizationSerializer
    )


def _expand(results, key, queryset, serializer):
    # DocumentCloud
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


def _extract_note_query(text_query):
    """Filter out all search fields"""
    tree = parser.parse(text_query)
    note_extractor = NoteExtractor()
    tree = note_extractor.visit(tree)
    if tree is None:
        return None
    return str(tree)


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

    note_query = _extract_note_query(text_query)
    if note_query is None:
        return text_query
    escaped_note_query = note_query.replace('"', '\\"')

    return_query = (
        # the original query to search for in documents
        f"({text_query}) "
        # search through notes which are public or that you own
        # on all documents you can view
        f"""
        _query_:"{{!join from=document_s fromIndex=notes to=id score=total
            v='+type:note +(access:public OR user:{user.pk})
               +(title:({escaped_note_query}) description:({escaped_note_query}))'
        }}"
        """
        # search through notes which are organization access
        # on all documents you can edit
        f"""
        _query_:"
            +(
                (
                    (user:{user.pk} OR projects_edit_access:({projects}))
                    AND access:(private organization)
                )
                OR
                (access:(public organization) AND organization:({organizations}))
            )
            +{{!join from=document_s fromIndex=notes to=id score=total
                v='+type:note +(access:organization)
                   +(title:({escaped_note_query}) description:({escaped_note_query}))'}}
            "
        """
    )
    # replace runs of white space with a single space - keeps the template readable
    # without incurring overhead of sending extra white space to solr
    return re.sub(r"\s+", " ", return_query)
