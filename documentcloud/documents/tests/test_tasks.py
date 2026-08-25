# Standard Library
from unittest.mock import patch

# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.choices import Status
from documentcloud.documents.models import Document
from documentcloud.documents.tasks import invalidate_cache, set_page_text
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
