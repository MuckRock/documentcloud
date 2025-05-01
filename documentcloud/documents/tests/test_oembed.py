# Django
from django.conf import settings
from django.test import RequestFactory

# Standard Library
from unittest import mock

# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.models import Document
from documentcloud.documents.oembed import DocumentOEmbed, NoteOEmbed, PageOEmbed
from documentcloud.oembed.utils import Query


class TestDocumentOEmbed:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.factory = RequestFactory()
        self.user = mock.MagicMock()
        self.document = mock.MagicMock(spec=Document)
        self.document.title = "Test Document"
        self.document.aspect_ratio = 1.5
        self.document.slug = "test-document"
        self.document.pk = 123
        self.document.get_absolute_url.return_value = (
            f"/documents/{self.document.pk}-{self.document.slug}/"
        )

        # Mock the Document manager
        self.document_queryset = mock.MagicMock()
        self.document_queryset.get_viewable.return_value = self.document_queryset
        self.document_queryset.get.return_value = self.document
        self.original_objects = Document.objects
        Document.objects = self.document_queryset

        # Create a DocumentOEmbed instance
        self.document_oembed = DocumentOEmbed()

        # Mock get_object_or_404
        self.get_object_patcher = mock.patch(
            "documentcloud.documents.oembed.get_object_or_404",
            return_value=self.document,
        )
        self.mock_get_object = self.get_object_patcher.start()
        
        yield
        
        # Teardown
        Document.objects = self.original_objects
        self.get_object_patcher.stop()

    def test_document_oembed_response(self):
        """Test the response method of DocumentOEmbed"""
        request = self.factory.get("/oembed/")
        request.user = self.user
        query = Query("responsive=1")

        response = self.document_oembed.response(
            request, query, max_width=600, max_height=None, pk=123
        )

        # Check response properties
        assert response["version"] == "1.0"
        assert response["type"] == "rich"
        assert response["title"] == "Test Document"
        assert response["width"] == 600
        assert response["height"] == 400

        # Check that the response contains an iframe with expected attributes
        assert '<iframe src="' in response["html"]
        assert f"{settings.DOCCLOUD_EMBED_URL}/documents/123-test-document/?responsive=1" in response["html"]
        assert 'title="Test Document (Hosted by DocumentCloud)"' in response["html"]
        assert 'width="600" height="400"' in response["html"]
        assert 'style="border: 1px solid #aaa; width: 100%; height: 800px;' in response["html"]
        assert 'sandbox="allow-scripts allow-same-origin allow-popups allow-forms' in response["html"]

    def test_document_oembed_get_dimensions(self):
        """Test the get_dimensions method of DocumentOEmbed"""
        # Test with both max_width and max_height - should preserve both dimensions
        width, height = self.document_oembed.get_dimensions(self.document, 600, 500)
        assert width == 600
        assert height == 500

        # Test with max_width less than default
        width, height = self.document_oembed.get_dimensions(self.document, 500, None)
        assert width == 500
        assert height == 333  # 500/1.5 = 333.33...

        # Test with only max_height
        width, height = self.document_oembed.get_dimensions(self.document, None, 450)
        assert width == 675  # 450*1.5 = 675
        assert height == 450

        # Test with no max dimensions
        width, height = self.document_oembed.get_dimensions(self.document, None, None)
        assert width == 800  # Should be default
        assert height == 533  # 800/1.5 = 533.33...

    def test_document_oembed_get_context(self):
        """Test the get_context method of DocumentOEmbed"""
        query = Query("param=value")
        extra = {"width": 600, "height": 400, "style": ""}

        context = self.document_oembed.get_context(self.document, query, extra)

        expected_src = f"{settings.DOCCLOUD_EMBED_URL}/documents/123-test-document/?param=value"
        assert context["src"] == expected_src
        assert context["width"] == 600
        assert context["height"] == 400
        assert context["style"] == ""

    def test_document_oembed_get_style(self):
        """Test the get_style method of DocumentOEmbed"""
        # Test responsive with no max dimensions
        style = self.document_oembed.get_style(None, None)
        assert style == " width: 100%; height: 800px; height: calc(100vh - 100px);"

        # Test with max_width only
        style = self.document_oembed.get_style(600, None)
        assert style == " width: 100%; height: 800px; height: calc(100vh - 100px); max-width: 600px;"

        # Test with max_height only
        style = self.document_oembed.get_style(None, 400)
        assert style == " width: 100%; height: 800px; height: calc(100vh - 100px); max-height: 400px;"

        # Test with both max dimensions
        style = self.document_oembed.get_style(600, 400)
        assert style == " width: 100%; height: 800px; height: calc(100vh - 100px); max-width: 600px; max-height: 400px;"


class TestPageOEmbed:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.factory = RequestFactory()
        self.user = mock.MagicMock()
        self.document = mock.MagicMock(spec=Document)
        self.document.pk = 123
        self.document.slug = "test-document"
        self.document.title = "Test Document"
        self.document.aspect_ratio = 1.5
        self.document.get_absolute_url.return_value = (
            f"/documents/{self.document.pk}-{self.document.slug}/"
        )

        # Mock the Document manager
        self.document_queryset = mock.MagicMock()
        self.document_queryset.get_viewable.return_value = self.document_queryset
        self.document_queryset.get.return_value = self.document
        self.original_objects = Document.objects
        Document.objects = self.document_queryset

        # Create a PageOEmbed instance
        self.page_oembed = PageOEmbed()

        # Mock get_object_or_404
        self.get_object_patcher = mock.patch(
            "documentcloud.documents.oembed.get_object_or_404",
            return_value=self.document,
        )
        self.mock_get_object = self.get_object_patcher.start()
        
        yield
        
        # Teardown
        Document.objects = self.original_objects
        self.get_object_patcher.stop()

    def test_page_oembed_response(self):
        """Test the response method of PageOEmbed"""
        request = self.factory.get("/oembed/")
        request.user = self.user
        query = Query("responsive=1")

        response = self.page_oembed.response(
            request, query, max_width=600, max_height=None, pk=123, page=1
        )

        # Check response properties
        assert response["version"] == "1.0"
        assert response["type"] == "rich"
        assert response["title"] == "Test Document"
        assert response["width"] == 600
        assert response["height"] == 400

        # Check that the response contains an iframe with expected attributes
        assert '<iframe src="' in response["html"]
        assert f"{settings.DOCCLOUD_EMBED_URL}/documents/123/pages/1/?responsive=1" in response["html"]
        assert 'title="Test Document (Hosted by DocumentCloud)"' in response["html"]
        assert 'width="600" height="400"' in response["html"]
        assert 'style="border: 1px solid #aaa; width: 100%; height: 800px;' in response["html"]
        assert 'sandbox="allow-scripts allow-same-origin allow-popups allow-forms' in response["html"]

    def test_page_oembed_get_dimensions(self):
        """Test the get_dimensions method of PageOEmbed"""
        # Test with max_width less than default
        width, height = self.page_oembed.get_dimensions(self.document, 500, None)
        assert width == 500
        assert height == 333

        # Test with max_width greater than default
        width, height = self.page_oembed.get_dimensions(self.document, 800, None)
        assert height == 533  # Should be calculated based on aspect ratio

        # Test with no max dimensions
        width, height = self.page_oembed.get_dimensions(self.document, None, None)
        assert width == 800  # Should be default
        assert height == 533  # Should be calculated based on aspect ratio

    def test_page_oembed_get_context(self):
        """Test the get_context method of PageOEmbed"""
        query = Query("param=value")
        extra = {"width": 600, "height": 400, "style": ""}

        context = self.page_oembed.get_context(self.document, query, extra, page=2)

        expected_src = f"{settings.DOCCLOUD_EMBED_URL}/documents/123/pages/2/?param=value"
        assert context["src"] == expected_src
        assert context["width"] == 600
        assert context["height"] == 400
        assert context["style"] == ""


class TestNoteOEmbed:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.factory = RequestFactory()
        self.user = mock.MagicMock()

        # Mock the Document
        self.document = mock.MagicMock(spec=Document)
        self.document.title = "Test Document"
        self.document.slug = "test-document"
        self.document.pk = 123
        self.document.get_absolute_url.return_value = (
            f"/documents/{self.document.pk}-{self.document.slug}/"
        )

        # Mock the Note
        self.note = mock.MagicMock()
        self.note.title = "Test Note"
        self.note.pk = 456

        # Mock Document.notes.get_viewable
        note_queryset = mock.MagicMock()
        note_queryset.get_viewable.return_value = note_queryset
        note_queryset.get.return_value = self.note
        self.document.notes = note_queryset

        # Mock the Document manager
        self.document_queryset = mock.MagicMock()
        self.document_queryset.get_viewable.return_value = self.document_queryset
        self.document_queryset.get.return_value = self.document
        self.original_objects = Document.objects
        Document.objects = self.document_queryset

        # Create a NoteOEmbed instance
        self.note_oembed = NoteOEmbed()

        # Mock get_object_or_404 for both document and note
        self.get_object_patcher = mock.patch(
            "documentcloud.documents.oembed.get_object_or_404",
            side_effect=[self.document, self.note],
        )
        self.mock_get_object = self.get_object_patcher.start()
        
        yield
        
        # Teardown
        Document.objects = self.original_objects
        self.get_object_patcher.stop()

    def test_note_oembed_response(self):
        """Test the response method of NoteOEmbed"""
        request = self.factory.get("/oembed/")
        request.user = self.user
        query = Query("responsive=1")

        response = self.note_oembed.response(
            request, query, max_width=600, max_height=None, doc_pk=123, pk=456
        )

        # Check response properties
        assert response["version"] == "1.0"
        assert response["type"] == "rich"
        assert response["title"] == "Test Note"

        # Check that the response contains an iframe with expected attributes
        assert '<iframe src="' in response["html"]
        assert f"{settings.DOCCLOUD_EMBED_URL}/documents/123/annotations/456/?responsive=1" in response["html"]
        assert 'title="Test Note (Hosted by DocumentCloud)"' in response["html"]
        assert 'width="100%" height="500px"' in response["html"]
        assert 'style="border: 1px solid #aaa;' in response["html"]
        assert 'sandbox="allow-scripts allow-same-origin allow-popups allow-forms' in response["html"]
