# Standard Library
from unittest import mock

# Third Party
import pytest
from listcrunch import uncrunch

# DocumentCloud
from documentcloud.documents.tests.factories import DocumentFactory


class TestDocumentModel:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.user = mock.MagicMock()
        self.document = DocumentFactory(
            id=2622,
            title=(
                "Agreement between Conservatives and"
                " Liberal Democrats to form a Coalition Government"
            ),
            slug=(
                "agreement-between-conservatives-and-liberal"
                "-democrats-to-form-a-coalition-government"
            ),
            page_spec="595.0x842.0:0-6",
        )
        self.document.page_spec = "595.0x842.0:0-6"

    @pytest.mark.django_db()
    def test_page_size(self):
        # just check that I set this up right
        assert self.document.page_spec == "595.0x842.0:0-6"
        assert uncrunch(self.document.page_spec) == [
            "595.0x842.0",
            "595.0x842.0",
            "595.0x842.0",
            "595.0x842.0",
            "595.0x842.0",
            "595.0x842.0",
            "595.0x842.0",
        ]

        width, height = self.document.page_size(0)
        assert width == 595.0
        assert height == 842.0

    @pytest.mark.django_db()
    def test_default_page_size(self):
        # only seven pages in this doc
        width, height = self.document.page_size(10)

        assert width == 8.5
        assert height == 11
