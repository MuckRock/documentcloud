# Django
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http.request import QueryDict

# Third Party
import pysolr
import pytest

# DocumentCloud
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.models import Document
from documentcloud.documents.search import search
from documentcloud.documents.tests.factories import DocumentFactory
from documentcloud.documents.tests.search_data import (
    DOCUMENTS,
    ORGANIZATIONS,
    PROJECTS,
    USERS,
)
from documentcloud.organizations.models import Organization
from documentcloud.organizations.tests.factories import OrganizationFactory
from documentcloud.projects.models import Project
from documentcloud.projects.tests.factories import ProjectFactory
from documentcloud.users.models import User
from documentcloud.users.tests.factories import UserFactory

# pylint: disable=too-many-public-methods


@pytest.yield_fixture(autouse=True, scope="module")
def setup(django_db_setup, django_db_blocker):
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
            for org in ORGANIZATIONS:
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
            for proj in PROJECTS:
                ProjectFactory(
                    id=proj["id"],
                    title=proj["title"],
                    user=users[proj["user"]],
                    documents=[documents[d] for d in proj["documents"]],
                    collaborators=[users[a] for a in proj["collaborators"]],
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
class TestSearch:

    default_query_string = "per_page=10&order=created_at"

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

        response = self.search("order=title")
        self.assert_documents(response["results"], sort_key="title", sort_reverse=False)

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

        response = self.search("data_edition=!")
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