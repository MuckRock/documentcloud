# Django
from django.utils import timezone

# Standard Library
import logging
from datetime import timedelta

# Third Party
import pytest
from requests.exceptions import HTTPError

# DocumentCloud
from documentcloud.documents.cache import (
    CACHE_TIERS,
    OLDEST_CACHE_TIER,
    CloudflarePurgeError,
    invalidate_cache_batch,
    tiered_cache_control,
)
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


class TestTieredCacheControl:
    """`tiered_cache_control` maps a document's age onto `CACHE_TIERS`.

    These assert against the table rather than against fixed seconds. The
    numbers are policy and expected to be retuned; what has to hold whatever
    they become is that a document lands in the band its age belongs to, that
    a boundary falls to the longer tier, and that TTLs never shrink as a
    document ages. Retuning the table should leave every test here passing.
    """

    # every tier as (max_age, s_maxage, stale_while_revalidate), oldest last
    ALL_TIERS = [tier[1:] for tier in CACHE_TIERS] + [OLDEST_CACHE_TIER]
    BOUNDS = [tier[0] for tier in CACHE_TIERS]

    @staticmethod
    def _directives(value):
        """Cache-Control as a dict, so assertions don't depend on ordering."""
        directives = {}
        for part in value.split(","):
            key, _, val = part.strip().partition("=")
            directives[key.lower()] = val or True
        return directives

    @staticmethod
    def _expected(tier):
        """The directives a given tier should produce."""
        max_age, s_maxage, stale_while_revalidate = tier
        expected = {
            "public": True,
            "max-age": str(max_age),
            "s-maxage": str(s_maxage),
        }
        if stale_while_revalidate is not None:
            expected["stale-while-revalidate"] = str(stale_while_revalidate)
        return expected

    @classmethod
    def _lower_edge(cls, index):
        """Smallest age that belongs to tier `index`."""
        return timedelta(0) if index == 0 else cls.BOUNDS[index - 1]

    @pytest.fixture
    def now(self):
        return timezone.now()

    def test_table_is_ordered_by_ascending_bound(self):
        """The lookup walks `CACHE_TIERS` in order and stops at the first
        bound the age falls under, so an out-of-order or duplicated bound
        would silently mis-tier every document past the misplaced row."""
        assert self.BOUNDS == sorted(self.BOUNDS)
        assert len(set(self.BOUNDS)) == len(self.BOUNDS)

    def test_ttls_never_shrink_as_documents_age(self):
        """The premise of the whole table: the longer since the last edit, the
        longer a cached copy stays correct. A retune may move any number, but
        it must not leave an older document with a shorter TTL than a younger
        one - that would be strictly worse than no tiering at all."""
        assert [tier[0] for tier in self.ALL_TIERS] == sorted(
            tier[0] for tier in self.ALL_TIERS
        )
        assert [tier[1] for tier in self.ALL_TIERS] == sorted(
            tier[1] for tier in self.ALL_TIERS
        )

    def test_browsers_are_never_trusted_longer_than_the_cdn(self):
        """`max-age` must not exceed `s-maxage` at any tier. A purge clears the
        edge but cannot reach a browser that already holds the response, so a
        browser TTL longer than the edge TTL would leave readers on a stale
        copy that no invalidation can recall."""
        for max_age, s_maxage, _ in self.ALL_TIERS:
            assert max_age <= s_maxage

    @pytest.mark.parametrize("index", range(len(ALL_TIERS)))
    def test_age_within_a_band_gets_that_band_tier(self, index, now):
        """Both edges of every configured band resolve to that band's tier."""
        lower = self._lower_edge(index)
        if index < len(self.BOUNDS):
            upper_inclusive = self.BOUNDS[index] - timedelta(seconds=1)
        else:
            # the oldest tier is open-ended
            upper_inclusive = lower + timedelta(days=10 * 365)
        for age in (lower, upper_inclusive):
            value = tiered_cache_control(now - age, now=now)
            assert self._directives(value) == self._expected(self.ALL_TIERS[index])

    @pytest.mark.parametrize("index", range(len(BOUNDS)))
    def test_boundary_belongs_to_the_longer_tier(self, index, now):
        """Each tier covers `age < bound`, so landing exactly on a boundary
        moves into the next, longer tier. Pinned because an off-by-one here
        silently mis-tiers a whole band of documents, in the unsafe direction
        if it ever flips to `<=`."""
        bound = self.BOUNDS[index]
        just_under = tiered_cache_control(now - bound + timedelta(seconds=1), now=now)
        exactly = tiered_cache_control(now - bound, now=now)
        assert self._directives(just_under) == self._expected(self.ALL_TIERS[index])
        assert self._directives(exactly) == self._expected(self.ALL_TIERS[index + 1])

    def test_stale_while_revalidate_only_where_the_tier_defines_it(self, now):
        """`None` in the table omits the directive rather than emitting an
        empty or zero value."""
        for index, tier in enumerate(self.ALL_TIERS):
            value = tiered_cache_control(now - self._lower_edge(index), now=now)
            present = "stale-while-revalidate" in self._directives(value)
            assert present is (tier[2] is not None)

    def test_future_timestamp_gets_the_shortest_tier(self, now):
        """Clock skew between the app and the database can put `updated_at`
        slightly ahead of now. Treat that as freshly edited rather than
        letting a negative age fall through to the longest tier."""
        value = tiered_cache_control(now + timedelta(minutes=5), now=now)
        assert self._directives(value) == self._expected(self.ALL_TIERS[0])

    def test_defaults_to_current_time(self, now):
        """`now` is injectable for tests but optional in production code."""
        value = tiered_cache_control(now)
        assert self._directives(value) == self._expected(self.ALL_TIERS[0])
