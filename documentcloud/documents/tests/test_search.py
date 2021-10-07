# Django
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http.request import QueryDict

# Standard Library
from datetime import datetime
from unittest.mock import Mock

# Third Party
import pysolr
import pytest
import pytz
from luqum.parser import parser

# DocumentCloud
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.models import Document
from documentcloud.documents.search import (
    BooleanDetector,
    DateValidator,
    FilterExtractor,
    _parse,
    search,
)
from documentcloud.documents.search_escape import escape
from documentcloud.documents.tests.factories import DocumentFactory, NoteFactory
from documentcloud.documents.tests.search_data import (
    DOCUMENTS,
    NOTES,
    ORGANIZATIONS,
    PROJECTS,
    USERS,
)
from documentcloud.organizations.models import Organization
from documentcloud.organizations.tests.factories import (
    OrganizationEntitlementFactory,
    OrganizationFactory,
)
from documentcloud.projects.models import Project
from documentcloud.projects.tests.factories import ProjectFactory
from documentcloud.users.models import User
from documentcloud.users.tests.factories import UserFactory

# pylint: disable=too-many-public-methods


@pytest.yield_fixture(scope="class")
def setup_solr(django_db_setup, django_db_blocker):
    """Set up the models for the search tests

    `django_db_setup` causes pytest to initiate the test database
    """
    # pylint: disable=unused-argument
    solr = pysolr.Solr(settings.SOLR_URL, auth=settings.SOLR_AUTH)
    with django_db_blocker.unblock():
        try:
            organizations = {}
            users = {}
            documents = {}
            notes = {}
            # this enables searching through notes for users in that org
            entitlement = OrganizationEntitlementFactory()
            for org in ORGANIZATIONS:
                if org.pop("entitlement", None) == "org":
                    org["entitlement"] = entitlement
                organizations[org["id"]] = OrganizationFactory(**org)
            for user in USERS:
                user = user.copy()
                org = user.pop("organization")
                users[user["id"]] = UserFactory(
                    membership__organization=organizations[org], **user
                )
            for doc in DOCUMENTS:
                doc = doc.copy()
                user = doc.pop("user")
                org = doc.pop("organization")
                documents[doc["id"]] = DocumentFactory(
                    user=users[user], organization=organizations[org], **doc
                )
            for note in NOTES:
                note = note.copy()
                user = note.pop("user")
                org = note.pop("organization")
                doc = note.pop("document")
                notes[note["id"]] = NoteFactory(
                    user=users[user],
                    organization=organizations[org],
                    document=documents[doc],
                    **note,
                )
            for proj in PROJECTS:
                ProjectFactory(
                    id=proj["id"],
                    title=proj["title"],
                    user=users[proj["user"]],
                    edit_documents=[documents[d] for d in proj["documents"]],
                    collaborators=[users[a] for a in proj["collaborators"]],
                    edit_collaborators=[users[a] for a in proj["edit_collaborators"]],
                )
            for doc in documents.values():
                solr.add([doc.solr()])
            solr.commit()
            yield
        finally:
            Document.objects.all().delete()
            Project.objects.all().delete()
            User.objects.all().delete()
            Organization.objects.all().delete()
            solr.delete(q="*:*")


@pytest.mark.django_db()
@pytest.mark.solr
@pytest.mark.usefixtures("setup_solr")
class TestSearch:

    default_query_string = "per_page=10&sort=created_at"

    def assert_documents(
        self,
        results,
        test=lambda d: True,
        public=True,
        slice_=slice(10),
        sort_key="created_at",
        sort_reverse=True,
    ):
        # pylint: disable=too-many-arguments
        expected_docs = [d for d in DOCUMENTS if test(d)]
        if public:
            expected_docs = [
                d
                for d in expected_docs
                if d["access"] == Access.public
                and d["status"] in [Status.success, Status.readable]
            ]
        expected_docs.sort(key=lambda d: d[sort_key], reverse=sort_reverse)
        assert [int(d["id"]) for d in results] == [
            d["id"] for d in expected_docs[slice_]
        ]

    def search(self, query_string, user=None):
        if user is None:
            user = AnonymousUser()
        else:
            user = User.objects.get(pk=user)
        return search(user, QueryDict(f"{self.default_query_string}&{query_string}"))

    def test_search(self):
        """Simple search test"""

        response = self.search("")
        self.assert_documents(response["results"])
        assert response["count"] == 11

    def test_search_page(self):
        """Test fetching a given page of results"""

        response = self.search("page=2")
        self.assert_documents(response["results"], slice_=slice(10, 20))

    def test_search_per_page(self):
        """Test fetching a different number of results per page"""

        response = self.search("per_page=5")
        self.assert_documents(response["results"], slice_=slice(5))

    def test_search_order(self):
        """Test fetching in a different order"""

        response = self.search("sort=title")
        self.assert_documents(response["results"], sort_key="title", sort_reverse=False)

    def test_search_expands(self):
        """Search with expanded users and organizations"""

        response = self.search("expand=user,organization")
        self.assert_documents(response["results"])
        assert response["count"] == 11
        assert "id" in response["results"][0]["user"]
        assert "id" in response["results"][0]["organization"]

    def test_search_query(self):
        """Test searching with some text"""

        query = "letter"

        def test(doc):
            return (
                query in doc.get("title", "").lower()
                or query in doc.get("source", "").lower()
                or query in doc.get("description", "").lower()
            )

        response = self.search(f"q={query}")
        self.assert_documents(response["results"], test=test)
        assert response["count"] == 4

    def test_search_user(self):
        """Test searching for a user"""

        response = self.search("user=1")
        self.assert_documents(response["results"], test=lambda d: d["user"] == 1)
        assert response["count"] == 2

    def test_search_user_negative(self):
        """Test searching for a user"""

        response = self.search("-user=1")
        self.assert_documents(response["results"], test=lambda d: d["user"] != 1)
        assert response["count"] == 9

    def test_search_users(self):
        """Test searching for a user"""

        response = self.search("user=1&user=2")
        self.assert_documents(response["results"], test=lambda d: d["user"] in [1, 2])
        assert response["count"] == 4

    def test_search_org(self):
        """Test searching for an organization"""

        response = self.search("organization=1")
        self.assert_documents(
            response["results"], test=lambda d: d["organization"] == 1
        )
        assert response["count"] == 4

    def test_search_access(self):
        """Test searching for an access"""

        response = self.search("access=private", user=1)
        self.assert_documents(
            response["results"],
            public=False,
            test=lambda d: d["access"] == Access.private,
        )
        assert response["count"] == 1

    def test_search_access_blank(self):
        """Test searching for a blank access - should not crash"""
        self.search("access=", user=1)

    def test_search_status(self):
        """Test searching for a status"""

        response = self.search("status=readable")
        self.assert_documents(
            response["results"], test=lambda d: d["status"] == Status.readable
        )
        assert response["count"] == 1

    def test_search_project(self):
        """Test searching for a project"""

        response = self.search("project=1")
        self.assert_documents(
            response["results"], test=lambda d: d["id"] in PROJECTS[0]["documents"]
        )
        assert response["count"] == 1

    def test_search_project_invalid(self):
        """Test searching for an invalid project - should not crash"""
        self.search("project=--1")

    def test_search_created_at(self):
        """Test searching by created_at date"""

        response = self.search("created_at=2011-01-01T00:00:00Z")
        self.assert_documents(
            response["results"],
            test=lambda d: d["created_at"] == datetime(2011, 1, 1, tzinfo=pytz.utc),
        )
        assert response["count"] == 1

    def test_search_created_at_invalid(self):
        """Test searching for an invalid project"""
        self.search("created_at=foo")

    def test_search_id(self):
        """Test searching for a document by id"""

        response = self.search("document=1")
        self.assert_documents(response["results"], test=lambda d: d["id"] == 1)
        assert response["count"] == 1

    def test_search_title(self):
        """Test searching for a document by title"""

        response = self.search("title=letter")
        self.assert_documents(
            response["results"], test=lambda d: "letter" in d["title"].lower()
        )
        assert response["count"] == 3

    def test_search_source(self):
        """Test searching for a document by source"""

        response = self.search("source=lex")
        self.assert_documents(
            response["results"], test=lambda d: "lex" in d.get("source", "").lower()
        )
        assert response["count"] == 1

    def test_search_description(self):
        """Test searching for a document by description"""

        response = self.search("description=friendly")
        self.assert_documents(
            response["results"],
            test=lambda d: "friendly" in d.get("description", "").lower(),
        )
        assert response["count"] == 1

    def test_search_data(self):
        """Test searching for a document by a data field for a given value"""

        response = self.search("data_edition=first")
        self.assert_documents(
            response["results"],
            test=lambda d: d.get("data", {}).get("edition") == "first",
        )
        assert response["count"] == 1

    def test_search_data_exists(self):
        """Test searching for a document by a data field existing"""

        response = self.search("data_edition=*")
        self.assert_documents(
            response["results"], test=lambda d: "edition" in d.get("data", {})
        )
        assert response["count"] == 2

    def test_search_data_not_exists(self):
        """Test searching for a document by a data field not existing"""

        response = self.search("-data_edition=*")
        self.assert_documents(
            response["results"], test=lambda d: "edition" not in d.get("data", {})
        )
        assert response["count"] == 9

    def test_search_private(self):
        """Test searching for a private document you cannot view"""

        response = self.search("document=3", user=2)
        assert response["count"] == 0

    def test_search_private_owner(self):
        """Test searching for a private document you own"""

        response = self.search("document=3", user=1)
        assert response["count"] == 1

    def test_search_invisible_owner(self):
        """Test searching for an invisible document you own"""

        response = self.search("document=16", user=6)
        assert response["count"] == 0

    def test_search_private_organization(self):
        """Test searching for a document shared via organization"""

        response = self.search("document=6", user=1)
        assert response["count"] == 1

    def test_search_private_project(self):
        """Test searching for a document shared via project"""

        response = self.search("document=3", user=3)
        assert response["count"] == 1

    @pytest.mark.parametrize(
        "user,doc,notes",
        [
            (None, 1, {"1"}),  # anonymous user my view public notes
            (2, 1, {"1", "2", "3"}),  # owner may view all notes
            (1, 1, {"1", "3"}),  # org collaborator may view public and org notes
            (3, 1, {"1"}),  # non-collaborator may view public notes
            (4, 1, {"1"}),  # proj collaborator cannot see org notes on public docs
            (5, 1, {"1"}),  # non-premium user my view public notes
            (7, 3, {"4", "6"}),  # proj collaborator may view public and org notes
        ],
    )
    def test_search_notes_returned(self, user, doc, notes):
        """Test that the proper notes are returned"""
        response = self.search(f"id={doc}", user=user)
        document = response["results"][0]
        assert len(document["notes"]) == len(notes)
        assert {n["id"] for n in document["notes"]} == notes

    @pytest.mark.parametrize(
        "user,note,viewable",
        [
            # anonymous may not search any notes
            (None, 0, False),
            (None, 1, False),
            (None, 2, False),
            # owner may search all notes
            (2, 0, True),
            (2, 1, True),
            (2, 2, True),
            # org collaborator may search public/org notes
            (1, 0, True),
            (1, 1, False),
            (1, 2, True),
            # non-collaborator may search public notes
            (3, 0, True),
            (3, 1, False),
            (3, 2, False),
            # project collaborator may not search org notes on public docs
            (4, 0, True),
            (4, 1, False),
            (4, 2, False),
            # non-premium may not search any notes
            (5, 0, False),
            (5, 1, False),
            (5, 2, False),
            # proj collaborator may search public/org notes
            (7, 3, True),
            (7, 4, False),
            (7, 5, True),
        ],
    )
    def test_search_notes_content(self, user, note, viewable):
        """Test that the proper notes are searchable for pro users
        """

        content = NOTES[note]["content"]
        doc = NOTES[note]["document"]
        response = self.search(f"q={content}", user=user)

        if viewable:
            assert len(response["results"]) == 1
            document = response["results"][0]
            assert document["id"] == str(doc)
        else:
            assert len(response["results"]) == 0


class TestBooleanDetector:
    @pytest.mark.parametrize(
        "query,has_bool",
        [
            ("a AND b", True),
            ("a OR b", True),
            ("(a OR b) AND c d", True),
            ("a NOT b", False),
            ("a b", False),
        ],
    )
    def test_detector(self, query, has_bool):
        tree = parser.parse(query)
        assert any(BooleanDetector().visit(tree)) is has_bool


class TestDateValidator:
    @pytest.mark.parametrize(
        "query,valid",
        [
            ("NOW", True),
            ("*", True),
            ("*+1DAY", False),
            ("*/DAY", False),
            ("2020-01-02T03:04:05Z", True),
            ("2020-01-02T03:04:05.06Z", True),
            ("2020-21-02T03:04:05Z", False),
            ("2020-02-30T03:04:05Z", False),
            ("2020-02-01T33:04:05Z", False),
            ("2020-02-01", False),
            ("NOW/YEAR", True),
            ("NOW/YEARS", True),
            ("NOW/DATE", True),
            ("NOW/DATES", False),
            ("2020-01-02T03:04:05Z/MINUTE", True),
            ("2020-01-02T03:04:05Z/1MINUTE", False),
            ("NOW-1MONTH", True),
            ("NOW+2MONTHS", True),
            ("NOW+2SECONDS-3MILLIS", True),
            ("NOW*2MONTHS", False),
            ("2020-01-02T03:04:05.06Z+1HOUR", True),
            ("NOW+2MONTHS/MONTH", True),
            ("NOW+2MONTHS+2DAYS/MONTH", True),
            ("NOW/YEAR+2MONTHS/MONTH+2DAYS/DAY", True),
            ("NOW/YEAR+NOW", False),
        ],
    )
    def test_validator(self, query, valid):
        tree = parser.parse(query)
        assert all(DateValidator().visit(tree)) is valid


class TestFilterExtractor:
    @pytest.mark.parametrize(
        "query,new_query,filters,sort_only,sort",
        [
            ("a user:1", "a", "user=1", False, None),
            ("user:1", "", "user=1", False, None),
            ("a -user:1", "a", "-user=1", False, None),
            ("a +user:1", "a", "user=1", False, None),
            ("a user:foo", "a user:foo", "", False, None),
            ('a user:"1"', "a", 'user="1"', False, None),
            ('a user:[1 TO "2"]', "a", 'user=[1 TO "2"]', False, None),
            ("a user:[a TO z]", "a user:[a TO z]", "", False, None),
            ("a user:(foo:1)", "a user:(foo:1)", "", False, None),
            ("a created_at:foo", "a created_at:foo", "", False, None),
            (
                'a created_at:"2020-01-02T03:04:05.6Z"',
                "a",
                'created_at="2020-01-02T03:04:05.6Z"',
                False,
                None,
            ),
            (
                'a created_at:"2020-13-02T03:04:05.6Z"',
                'a created_at:"2020-13-02T03:04:05.6Z"',
                "",
                False,
                None,
            ),
            (
                "a created_at:2020-01-02T03:04:05Z",
                "a",
                "created_at=2020-01-02T03\\:04\\:05Z",
                False,
                None,
            ),
            (
                'a created_at:[2020-01-02T03:04:05Z TO "2020-01-02T03:04:06Z"]',
                "a",
                'created_at=[2020-01-02T03\\:04\\:05Z TO "2020-01-02T03:04:06Z"]',
                False,
                None,
            ),
            (
                "a created_at:[2020-01-02T03:04:05Z TO *]",
                "a",
                "created_at=[2020-01-02T03\\:04\\:05Z TO *]",
                False,
                None,
            ),
            (
                "a created_at:[2020-01-02T03:04:05Z TO NOW-1DAY/DAY]",
                "a",
                "created_at=[2020-01-02T03\\:04\\:05Z TO NOW-1DAY/DAY]",
                False,
                None,
            ),
            ("a created_at:[a TO z]", "a created_at:[a TO z]", "", False, None),
            ("a title:foo", "a title:foo", "", False, None),
            ("a account:1", "a", "user=1", False, None),
            ("a data_foo:1", "a", "data_foo=1", False, None),
            ("a data_foo?:1", "a data_foo?:1", "", False, None),
            ("a user:1 user:2", "a", "user=1&user=2", False, None),
            ("a user:(1 2)", "a", "user=(1 2)", False, None),
            ("a user:foo-1", "a", "user=1", False, None),
            ('a user:"foo-1"', "a", 'user="1"', False, None),
            ("a user:(foo-1 bar-2)", "a", "user=(1 2)", False, None),
            ("a user:1 organization:2", "a", "user=1&organization=2", False, None),
            ("a user:1 sort:title", "a", "user=1", False, "title"),
            ("a user:1 sort:title", "a user:1", "", True, "title"),
            ("a (user:1 AND sort:title)", "a (user:1)", "", True, "title"),
        ],
    )
    def test_extract_filter(self, query, new_query, filters, sort_only, sort):
        tree = parser.parse(query)
        filter_extractor = FilterExtractor(sort_only=sort_only)
        tree = filter_extractor.visit(tree)

        assert new_query == (str(tree) if tree else "")
        assert filter_extractor.filters == QueryDict(filters)
        assert filter_extractor.sort == sort


class TestParse:
    @pytest.mark.parametrize(
        "query,query_params,new_query,filters,sort,escaped,use_hl",
        [
            ("", "", "*:*", "", None, False, False),
            ("user:1", "", "*:*", "user=1", None, False, False),
            (
                "user:1 OR access:public",
                "",
                "user:1 OR access:public",
                "",
                None,
                False,
                False,
            ),
            ("user:foo-1", "", "*:*", "user=1", None, False, False),
            (
                "user:foo-1 OR access:public",
                "",
                "user:1 OR access:public",
                "",
                None,
                False,
                False,
            ),
            ("foo", "", "foo", "", None, False, False),
            ("foo sort:title", "", "foo", "", "title", False, False),
            ("foo", "title=bar", "foo title:(bar)", "", None, False, False),
            ("foo", "user=1", "foo", "", None, False, False),
            ("foo AND", "", 'foo "AND"', "", None, True, False),
            ("foo (", "", "foo \\(", "", None, True, False),
            ("foo~1", "", "foo~1", "", None, False, False),
            ("foo hl:true", "", "foo", "", None, False, True),
            ("foo~1 hl:true", "", "foo~1", "", None, False, False),
        ],
    )
    def test_auth_parse(
        self, query, query_params, new_query, filters, sort, escaped, use_hl
    ):
        # pylint: disable=too-many-arguments
        user = Mock()
        user.is_authenticated = True
        assert _parse(query, QueryDict(query_params, mutable=True), user) == (
            new_query,
            QueryDict(filters),
            sort,
            escaped,
            use_hl,
        )

    @pytest.mark.parametrize(
        "query,query_params,new_query,filters,sort,escaped,use_hl",
        [
            ("", "", "*:*", "", None, False, False),
            ("abc*", "", "abc\\*", "", None, False, False),
            ("abc~2", "", "abc", "", None, False, False),
            ("abc~ *", "", "abc \\*", "", None, False, False),
        ],
    )
    def test_anon_parse(
        self, query, query_params, new_query, filters, sort, escaped, use_hl
    ):
        # pylint: disable=too-many-arguments
        assert _parse(
            query, QueryDict(query_params, mutable=True), AnonymousUser()
        ) == (new_query, QueryDict(filters), sort, escaped, use_hl)


class TestEscape:
    @pytest.mark.parametrize(
        "query,escaped",
        [
            ("foo:bar (", "foo:bar \\("),
            ("foo:bar :foo", "foo:bar \\:foo"),
            ("foo:bar foo:", "foo:bar foo\\:"),
            ("foo:bar :", "foo:bar \\:"),
            ("foo:bar+baz", "foo:bar\\+baz"),
            ("foo (", "foo \\("),
            ("foo )", "foo \\)"),
            ("foo [", "foo \\["),
            ("foo ]", "foo \\]"),
            ("foo {", "foo \\{"),
            ("foo }", "foo \\}"),
            ("foo ~", "foo \\~"),
            ("foo ^", "foo \\^"),
            ("foo + ", "foo \\+"),
            ("foo - ", "foo \\-"),
            ("foo !", "foo \\!"),
            ("foo /", "foo \\/"),
            ("foo \\", "foo \\\\"),
            ('foo "', 'foo \\"'),
            ("foo + AND", 'foo \\+ "AND"'),
            ("foo AND", 'foo "AND"'),
            ("foo OR", 'foo "OR"'),
            ("foo NOT", 'foo "NOT"'),
            ('foo "(" )', 'foo "(" \\)'),
            ('foo "(" "', 'foo \\"\\(\\" \\"'),
            (
                "foo:foo AND (:bar OR baz:) (qux:qux AND",
                'foo:foo "AND" \\(\\:bar "OR" baz:\\) qux:qux "AND"',
            ),
        ],
    )
    def test_escape(self, query, escaped):
        assert escape(query) == escaped
