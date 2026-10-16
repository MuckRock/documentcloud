# Django
from django.contrib.admin.sites import AdminSite

# Standard Library
from unittest.mock import Mock

# Third Party
import pytest

# DocumentCloud
from documentcloud.core.tests import run_commit_hooks
from documentcloud.documents.admin import DocumentAdmin
from documentcloud.documents.choices import Access
from documentcloud.documents.models import Document
from documentcloud.documents.tests.factories import DocumentFactory


@pytest.mark.django_db()
class TestDocumentAdmin:
    def test_admin_edit_purges_cache(self, mocker):
        """Admin can make a document public without `update_access`."""
        mock_invalidate = mocker.patch(
            "documentcloud.documents.tasks.invalidate_cache.delay"
        )
        document = DocumentFactory(access=Access.private)
        document.access = Access.public
        form = Mock(changed_data=["access"])

        DocumentAdmin(Document, AdminSite()).save_model(
            Mock(), document, form, change=True
        )
        run_commit_hooks()

        mock_invalidate.assert_called_once_with(document.pk)
