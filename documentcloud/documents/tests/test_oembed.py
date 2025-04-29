from django.conf import settings
from django.test import RequestFactory, TestCase
from unittest import mock
from documentcloud.documents.models import Document
from documentcloud.documents.oembed import PageOEmbed
from documentcloud.oembed.utils import Query


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
    self.assertEqual(
      response["html"],
      f'<iframe src="{settings.DOCCLOUD_EMBED_URL}/documents/123/?responsive=1#document/p1" title="Test Document (Hosted by DocumentCloud)" width="600" height="400" style="border: 1px solid #aaa; width: 100%; height: 800px; height: calc(100vh - 100px); max-width: 600px;" sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-popups-to-escape-sandbox"></iframe>' # pylint:disable=line-too-long
    )
    
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