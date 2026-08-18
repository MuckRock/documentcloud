# Standard Library
from unittest.mock import patch

# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.choices import Status
from documentcloud.documents.models import Document
from documentcloud.documents.tasks import set_page_text
from documentcloud.documents.tests.factories import DocumentFactory


@pytest.mark.django_db
def test_set_page_text_does_not_clobber_data():
    doc = DocumentFactory(status=Status.pending, slug="test-doc")

    def fake_set_page_text(self):
        # simulate the Add-On writing a key/value pair into data via a
        # separate DB row update while this task holds a stale instance
        Document.objects.filter(pk=self.pk).update(data={"_tag": "applied"})
        return {"pages": [], "updated": 123}

    with patch.object(Document, "set_page_text", fake_set_page_text):
        set_page_text(doc.pk, [{"page_number": 0, "text": "hi"}])

    doc.refresh_from_db()
    assert doc.data == {"_tag": "applied"}  # survives with the fix
    assert doc.status == Status.success
