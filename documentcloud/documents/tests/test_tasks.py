# Django
from django.test.utils import override_settings
from django.utils import timezone

# Standard Library
from datetime import timedelta
from unittest.mock import patch

# Third Party
import pytest
from requests import Response
from requests.exceptions import HTTPError

# DocumentCloud
from documentcloud.core.tests import run_commit_hooks
from documentcloud.documents.choices import Access, Status
from documentcloud.documents.models import Document
from documentcloud.documents.tasks import (
    fetch_file_url,
    invalidate_cache,
    post_process,
    publish_scheduled_documents,
    set_page_text,
    update_access,
)
from documentcloud.documents.tests.factories import DocumentFactory


@pytest.mark.django_db()
class TestInvalidateCacheTask:
    """The `invalidate_cache` task batches purges and clears `cache_dirty`."""

    def test_accepts_single_pk(self, mocker):
        """A single pk arg purges one document."""
        mock_batch = mocker.patch(
            "documentcloud.documents.tasks.invalidate_cache_batch"
        )
        document = DocumentFactory(cache_dirty=True)

        invalidate_cache(document.pk)

        mock_batch.assert_called_once()
        (documents,) = mock_batch.call_args[0]
        assert [d.pk for d in documents] == [document.pk]
        document.refresh_from_db()
        assert document.cache_dirty is False

    def test_accepts_many_pks(self, mocker):
        """Several pk args are purged in a single batch."""
        mock_batch = mocker.patch(
            "documentcloud.documents.tasks.invalidate_cache_batch"
        )
        documents = DocumentFactory.create_batch(3, cache_dirty=True)

        invalidate_cache(*[d.pk for d in documents])

        assert mock_batch.call_count == 1
        (called,) = mock_batch.call_args[0]
        assert {d.pk for d in called} == {d.pk for d in documents}
        for document in documents:
            document.refresh_from_db()
            assert document.cache_dirty is False

    def test_clears_dirty_without_bumping_updated_at(self, mocker):
        """Clearing the flag must not look like a content edit.

        `updated_at` is an `AutoLastModifiedField`; bumping it on every purge
        would silently reset the freshness signal (3) and demote the document
        to the shortest TTL tier (4). The flag is cleared with a queryset
        `.update()` precisely so `save()` (and the field) never fires.
        """
        mocker.patch("documentcloud.documents.tasks.invalidate_cache_batch")
        document = DocumentFactory(cache_dirty=True)
        original_updated_at = document.updated_at

        invalidate_cache(document.pk)

        document.refresh_from_db()
        assert document.cache_dirty is False
        assert document.updated_at == original_updated_at


def _http_error(status_code):
    """Build an HTTPError carrying a response with the given status code"""
    response = Response()
    response.status_code = status_code
    return HTTPError(f"{status_code} Error", response=response)


@pytest.mark.django_db()
class TestFetchFileUrlTask:
    """The `fetch_file_url` task retries 5xx errors and logs everything else."""

    def test_5xx_is_retried(self, mocker):
        """A 5xx response re-raises so celery's autoretry can retry it."""
        mocker.patch(
            "documentcloud.documents.tasks.storage.fetch_url",
            side_effect=_http_error(503),
            create=True,
        )
        document = DocumentFactory()

        with pytest.raises(HTTPError):
            fetch_file_url("https://example.com/doc.pdf", document.pk, False, "tess4")

        document.refresh_from_db()
        assert document.status != Status.error
        assert not document.errors.exists()

    def test_5xx_past_max_retries_is_logged(self, mocker):
        """A 5xx response after the final retry marks the document as errored."""
        mocker.patch(
            "documentcloud.documents.tasks.storage.fetch_url",
            side_effect=_http_error(503),
            create=True,
        )
        mocker.patch.object(fetch_file_url, "max_retries", 0)
        document = DocumentFactory()

        fetch_file_url("https://example.com/doc.pdf", document.pk, False, "tess4")

        document.refresh_from_db()
        assert document.status == Status.error
        assert document.errors.count() == 1

    def test_4xx_is_not_retried(self, mocker):
        """A 4xx response is logged immediately without retrying."""
        mocker.patch(
            "documentcloud.documents.tasks.storage.fetch_url",
            side_effect=_http_error(404),
            create=True,
        )
        document = DocumentFactory()

        fetch_file_url("https://example.com/doc.pdf", document.pk, False, "tess4")

        document.refresh_from_db()
        assert document.status == Status.error
        assert document.errors.count() == 1


@pytest.mark.django_db
def test_set_page_text_does_not_clobber_data():
    doc = DocumentFactory(status=Status.pending, slug="test-doc")

    def fake_set_page_text(self, *args, **kwargs):
        # simulate the Add-On writing a key/value pair into data via a
        # separate DB row update while this task holds a stale instance
        Document.objects.filter(pk=self.pk).update(data={"_tag": "applied"})
        return {"pages": [], "updated": 123}

    with patch.object(Document, "set_page_text", fake_set_page_text):
        set_page_text(doc.pk, [{"page_number": 0, "text": "hi"}])

    doc.refresh_from_db()
    assert doc.data == {"_tag": "applied"}  # survives with the fix
    assert doc.status == Status.success


@pytest.mark.django_db()
class TestPurgeOnBecomingVisible:
    """Becoming visible to anonymous users purges any cached 404."""

    @pytest.fixture(autouse=True)
    def mock_invalidate(self, mocker):
        return mocker.patch("documentcloud.documents.tasks.invalidate_cache.delay")

    @pytest.fixture()
    def mock_storage(self, mocker):
        return mocker.patch("documentcloud.documents.tasks.storage")

    @override_settings(UPDATE_ACCESS_CHUNK_SIZE=2)
    def test_update_access_final_chunk_purges(self, mock_storage, mock_invalidate):
        """The final chunk is when `access` actually flips to public."""
        document = DocumentFactory(access=Access.private, status=Status.readable)
        mock_storage.list.return_value = ["a"]

        update_access(document.pk, Status.success, Access.public)
        run_commit_hooks()

        document.refresh_from_db()
        assert document.access == Access.public
        mock_invalidate.assert_called_once_with(document.pk)

    @override_settings(UPDATE_ACCESS_CHUNK_SIZE=2)
    def test_publish_scheduled_documents_purges(
        self, mocker, mock_storage, mock_invalidate
    ):
        """Scheduled publishing purges once `update_access` finishes."""
        mock_update_access = mocker.patch(
            "documentcloud.documents.tasks.update_access.delay"
        )
        document = DocumentFactory(
            access=Access.private,
            status=Status.success,
            publish_at=timezone.now() - timedelta(minutes=1),
        )
        mock_storage.list.return_value = ["a"]

        publish_scheduled_documents()
        run_commit_hooks()
        mock_update_access.assert_called_once()
        update_access(*mock_update_access.call_args[0])
        run_commit_hooks()

        document.refresh_from_db()
        assert document.access == Access.public
        mock_invalidate.assert_called_once_with(document.pk)

    def test_set_page_text_public_purges(self, mock_invalidate):
        """`set_page_text` moves a public upload out of `pending`."""
        document = DocumentFactory(access=Access.public, status=Status.pending)

        with patch.object(Document, "set_page_text", return_value={}):
            set_page_text(document.pk, [{"page_number": 0, "text": "hi"}])
        run_commit_hooks()

        mock_invalidate.assert_called_once_with(document.pk)

    def test_post_process_public_purges(self, mock_invalidate):
        """Modifications finish here, outside the view's completion path."""
        document = DocumentFactory(access=Access.public, status=Status.pending)

        post_process(document.pk, {"modifications": [], "pagespec": ""})
        run_commit_hooks()

        mock_invalidate.assert_called_once_with(document.pk)
