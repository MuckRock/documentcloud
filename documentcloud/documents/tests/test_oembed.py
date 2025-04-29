from django.conf import settings
from django.test import RequestFactory, TestCase
from unittest import mock
from documentcloud.documents.models import Document
from documentcloud.documents.oembed import DocumentOEmbed, PageOEmbed
from documentcloud.oembed.utils import Query

class DocumentOEmbedTest(TestCase):
  def setUp(self):
    self.factory = RequestFactory()
    self.user = mock.MagicMock()
    self.document = mock.MagicMock(spec=Document)
    self.document.title = "Test Document"
    self.document.aspect_ratio = 1.5
    self.document.get_absolute_url.return_value = "/documents/123/"
    
    # Mock the Document manager
    self.document_queryset = mock.MagicMock()
    self.document_queryset.get_viewable.return_value = self.document_queryset
    Document.objects = self.document_queryset
    
    # Create a DocumentOEmbed instance
    self.document_oembed = DocumentOEmbed()
    
    # Mock get_object_or_404
    self.get_object_mock = mock.patch(
      "documentcloud.documents.oembed.get_object_or_404", 
      return_value=self.document
    )

  def test_document_oembed_response(self):
    """Test the response method of DocumentOEmbed"""
    request = self.factory.get("/oembed/")
    request.user = self.user
    query = Query("responsive=1")
    
    with self.get_object_mock:
      response = self.document_oembed.response(
        request, query, max_width=600, max_height=None, pk=123
      )
    
    # Check response properties
    self.assertEqual(response["version"], "1.0")
    self.assertEqual(response["type"], "rich")
    self.assertEqual(response["title"], "Test Document")
    self.assertEqual(response["width"], 600)
    self.assertEqual(response["height"], 400)
    
    # Check that the response contains an iframe with expected attributes
    self.assertIn('<iframe src="', response["html"])
    self.assertIn(f'{settings.DOCCLOUD_EMBED_URL}/documents/123/?responsive=1', response["html"])
    self.assertIn('title="Test Document (Hosted by DocumentCloud)"', response["html"])
    self.assertIn('width="600" height="400"', response["html"])
    self.assertIn('style="border: 1px solid #aaa; width: 100%; height: 800px;', response["html"])
    self.assertIn('sandbox="allow-scripts allow-same-origin allow-popups allow-forms', response["html"])
    
  def test_document_oembed_get_dimensions(self):
    """Test the get_dimensions method of DocumentOEmbed"""
    # Test with both max_width and max_height - should preserve both dimensions
    width, height = self.document_oembed.get_dimensions(self.document, 600, 500)
    self.assertEqual(width, 600)
    self.assertEqual(height, 500)
    
    # Test with max_width less than default
    width, height = self.document_oembed.get_dimensions(self.document, 500, None)
    self.assertEqual(width, 500)
    self.assertEqual(height, 333)  # 500/1.5 = 333.33...
    
    # Test with only max_height
    width, height = self.document_oembed.get_dimensions(self.document, None, 450)
    self.assertEqual(width, 675)  # 450*1.5 = 675
    self.assertEqual(height, 450)
    
    # Test with no max dimensions
    width, height = self.document_oembed.get_dimensions(self.document, None, None)
    self.assertEqual(width, 800)  # Should be default
    self.assertEqual(height, 533)  # 800/1.5 = 533.33...

  def test_document_oembed_get_context(self):
    """Test the get_context method of DocumentOEmbed"""
    query = Query("param=value")
    extra = {"width": 600, "height": 400, "style": ""}
    
    context = self.document_oembed.get_context(self.document, query, extra)
    
    expected_src = f"{settings.DOCCLOUD_EMBED_URL}/documents/123/?param=value"
    self.assertEqual(context["src"], expected_src)
    self.assertEqual(context["width"], 600)
    self.assertEqual(context["height"], 400)
    self.assertEqual(context["style"], "")
    
  def test_document_oembed_get_style(self):
    """Test the get_style method of DocumentOEmbed"""
    # Test responsive with no max dimensions
    style = self.document_oembed.get_style(True, None, None)
    self.assertEqual(style, " width: 100%; height: 800px; height: calc(100vh - 100px);")
    
    # Test with max_width only
    style = self.document_oembed.get_style(True, 600, None)
    self.assertEqual(style, " width: 100%; height: 800px; height: calc(100vh - 100px); max-width: 600px;")
    
    # Test with max_height only
    style = self.document_oembed.get_style(True, None, 400)
    self.assertEqual(style, " width: 100%; height: 800px; height: calc(100vh - 100px); max-height: 400px;")
    
    # Test with both max dimensions
    style = self.document_oembed.get_style(True, 600, 400)
    self.assertEqual(style, " width: 100%; height: 800px; height: calc(100vh - 100px); max-width: 600px; max-height: 400px;")

class PageOEmbedTest(TestCase):
  def setUp(self):
    self.factory = RequestFactory()
    self.user = mock.MagicMock()
    self.document = mock.MagicMock(spec=Document)
    self.document.title = "Test Document"
    self.document.aspect_ratio = 1.5
    self.document.get_absolute_url.return_value = "/documents/123/"
    
    # Mock the Document manager
    self.document_queryset = mock.MagicMock()
    self.document_queryset.get_viewable.return_value = self.document_queryset
    Document.objects = self.document_queryset
    
    # Create a PageOEmbed instance
    self.page_oembed = PageOEmbed()
    
    # Mock get_object_or_404
    self.get_object_mock = mock.patch(
      "documentcloud.documents.oembed.get_object_or_404", 
      return_value=self.document
    )

  def test_page_oembed_response(self):
    """Test the response method of PageOEmbed"""
    request = self.factory.get("/oembed/")
    request.user = self.user
    query = Query("responsive=1")
    
    with self.get_object_mock:
      response = self.page_oembed.response(
        request, query, max_width=600, max_height=None, pk=123, page=1
      )
    
    # Check response properties
    self.assertEqual(response["version"], "1.0")
    self.assertEqual(response["type"], "rich")
    self.assertEqual(response["title"], "Test Document")
    self.assertEqual(response["width"], 600)
    self.assertEqual(response["height"], 400)
    
    # Check that the response contains an iframe with expected attributes
    self.assertIn('<iframe src="', response["html"])
    self.assertIn(f'{settings.DOCCLOUD_EMBED_URL}/documents/123/?responsive=1#document/p1', response["html"])
    self.assertIn('title="Test Document (Hosted by DocumentCloud)"', response["html"])
    self.assertIn('width="600" height="400"', response["html"])
    self.assertIn('style="border: 1px solid #aaa; width: 100%; height: 800px;', response["html"])
    self.assertIn('sandbox="allow-scripts allow-same-origin allow-popups allow-forms', response["html"])
    
  def test_page_oembed_get_dimensions(self):
    """Test the get_dimensions method of PageOEmbed"""
    # Test with max_width less than default
    width, height = self.page_oembed.get_dimensions(self.document, 500, None)
    self.assertEqual(width, 500)
    self.assertEqual(height, 333)  
    
    # Test with max_width greater than default
    width, height = self.page_oembed.get_dimensions(self.document, 800, None)
    self.assertEqual(height, 533)  # Should be calculated based on aspect ratio
    
    # Test with no max dimensions
    width, height = self.page_oembed.get_dimensions(self.document, None, None)
    self.assertEqual(width, 800)  # Should be default
    self.assertEqual(height, 533)  # Should be calculated based on aspect ratio

  def test_page_oembed_get_context(self):
    """Test the get_context method of PageOEmbed"""
    query = Query("param=value")
    extra = {"width": 600, "height": 400, "style": ""}
    
    context = self.page_oembed.get_context(self.document, query, extra, page=2)
    
    expected_src = f"{settings.DOCCLOUD_EMBED_URL}/documents/123/?param=value#document/p2"
    self.assertEqual(context["src"], expected_src)
    self.assertEqual(context["width"], 600)
    self.assertEqual(context["height"], 400)
    self.assertEqual(context["style"], "")