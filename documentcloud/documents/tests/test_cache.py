# Standard Library
import logging

# Third Party
import pytest
from requests.exceptions import HTTPError

# DocumentCloud
from documentcloud.documents.cache import CloudflarePurgeError, invalidate_cache_batch
from documentcloud.documents.choices import Access
from documentcloud.documents.tests.factories import DocumentFactory


@pytest.mark.django_db()
class TestDocumentCacheInvalidation:
    """`invalidate_cache_batch` purges the API by Cache-Tag and URLs by URL."""

    @pytest.fixture(autouse=True)
    def cache_settings(self, settings):
        settings.CLOUDFLARE_API_ZONE = "zone123"
        settings.CLOUDFLARE_API_EMAIL = "cache@example.com"
        settings.CLOUDFLARE_API_KEY = "secret"
        settings.CLOUDFLARE_HOSTS = ["https://www.example.com"]
        settings.CLOUDFRONT_DISTRIBUTION_ID = ""
        settings.PUBLIC_ASSET_URL = "https://assets.example.com/documents/"

    @pytest.fixture
    def mock_post(self, mocker):
        return mocker.patch("documentcloud.documents.cache.requests.post")

    def test_cache_tag(self):
        """The Cache-Tag is `doc-{pk}`."""
        document = DocumentFactory()
        assert document.cache_tag == f"doc-{document.pk}"

    def test_batch_purges_tag_and_urls(self, mock_post):
        """One Cloudflare request purges the `doc-{id}` tag, another the URLs.

        `files` and `tags` are mutually exclusive in a single zone purge
        request, so they must be sent separately.
        """
        document = DocumentFactory()

        invalidate_cache_batch([document])

        assert mock_post.call_count == 2
        payloads = [call.kwargs["json"] for call in mock_post.call_args_list]
        tags_payload = next(p for p in payloads if "tags" in p)
        files_payload = next(p for p in payloads if "files" in p)
        assert tags_payload["tags"] == [f"doc-{document.pk}"]
        assert (
            f"https://www.example.com{document.get_absolute_url()}"
            in files_payload["files"]
        )
        # never both keys in one request
        assert all(("tags" in p) != ("files" in p) for p in payloads)

    def test_batch_always_purges_frontend_urls_even_when_private(self, mock_post):
        """On a public -> private flip `access` is already private by purge
        time, so the frontend URLs must be purged unconditionally (5b) - the
        public copy may still be cached at the edge."""
        document = DocumentFactory(access=Access.private)

        invalidate_cache_batch([document])

        files_payload = next(
            call.kwargs["json"]
            for call in mock_post.call_args_list
            if "files" in call.kwargs["json"]
        )
        assert (
            f"https://www.example.com{document.get_absolute_url()}"
            in files_payload["files"]
        )

    def test_batch_chunks_to_the_purge_limit(self, mock_post, settings):
        """Each purge request is chunked to the configured cap."""
        settings.CLOUDFLARE_PURGE_LIMIT = 2
        documents = DocumentFactory.create_batch(3)

        invalidate_cache_batch(documents)

        # 3 tags -> chunks of 2 -> 2 requests
        # 3 docs x (1 host + 1 asset) = 6 files -> chunks of 2 -> 3 requests
        assert mock_post.call_count == 5

    def test_batch_no_op_without_zone(self, mock_post, settings):
        """No Cloudflare zone configured means no purge request."""
        settings.CLOUDFLARE_API_ZONE = ""
        document = DocumentFactory()

        invalidate_cache_batch([document])

        mock_post.assert_not_called()

    def test_batch_empty_is_noop(self, mock_post):
        """An empty batch issues no requests."""
        invalidate_cache_batch([])
        mock_post.assert_not_called()

    @pytest.mark.usefixtures("mock_post")
    def test_batch_purges_cloudfront_paths(self, mocker, settings):
        """CloudFront is invalidated by path for every document in the batch."""
        settings.CLOUDFRONT_DISTRIBUTION_ID = "DIST123"
        mock_boto = mocker.patch("documentcloud.documents.cache.boto3")
        documents = DocumentFactory.create_batch(2)

        invalidate_cache_batch(documents)

        create_invalidation = mock_boto.client.return_value.create_invalidation
        create_invalidation.assert_called_once()
        paths = create_invalidation.call_args.kwargs["InvalidationBatch"]["Paths"]
        assert paths["Quantity"] == 2

    def test_batch_logs_and_raises_when_cloudflare_rejects(self, mock_post, caplog):
        """A 200 with `success: false` is a failure: it's logged and raised so
        the task retries."""
        response = mock_post.return_value
        response.ok = True
        response.json.return_value = {"success": False, "errors": ["bad zone"]}

        with caplog.at_level(logging.ERROR):
            with pytest.raises(CloudflarePurgeError):
                invalidate_cache_batch([DocumentFactory()])

        assert "Cloudflare cache purge failed" in caplog.text

    def test_batch_raises_on_http_error(self, mock_post):
        """A bad HTTP status raises (via raise_for_status) so the task retries."""
        response = mock_post.return_value
        response.ok = False
        response.status_code = 500
        response.raise_for_status.side_effect = HTTPError("500 Server Error")

        with pytest.raises(HTTPError):
            invalidate_cache_batch([DocumentFactory()])

    def test_batch_logs_rate_limit_as_warning(self, mock_post, caplog):
        """A 429 is expected under burst load - logged as a warning, not an
        error, but still raised so the task retries with backoff."""
        response = mock_post.return_value
        response.ok = False
        response.status_code = 429
        response.raise_for_status.side_effect = HTTPError("429 Too Many Requests")

        with caplog.at_level(logging.WARNING):
            with pytest.raises(HTTPError):
                invalidate_cache_batch([DocumentFactory()])

        assert any(record.levelno == logging.WARNING for record in caplog.records)
        assert not any(record.levelno >= logging.ERROR for record in caplog.records)
