# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.tasks import invalidate_cache
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
