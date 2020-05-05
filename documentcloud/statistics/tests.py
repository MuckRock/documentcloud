# Standard Library
from datetime import date, timedelta

# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.choices import Access
from documentcloud.documents.tests.factories import DocumentFactory, NoteFactory
from documentcloud.projects.tests.factories import ProjectFactory
from documentcloud.statistics.models import Statistics
from documentcloud.statistics.tasks import store_statistics


@pytest.mark.django_db()
def test_store_statistics():
    documents = []
    doc_data = [
        (Access.public, 10, 10),
        (Access.organization, 20, 20),
        (Access.private, 30, 30),
        (Access.invisible, 1, 40),
    ]
    for access, num, page_count in doc_data:
        documents.extend(
            DocumentFactory.create_batch(num, access=access, page_count=page_count)
        )
    note_data = [
        (Access.public, 35),
        (Access.organization, 25),
        (Access.private, 15),
        (Access.invisible, 0),
    ]
    for access, num in note_data:
        NoteFactory.create_batch(num, access=access, document=documents[0])
    num_projects = 42
    ProjectFactory.create_batch(num_projects)
    store_statistics()
    stats = Statistics.objects.first()
    assert stats.date == date.today() - timedelta(1)
    assert stats.total_documents == sum(d[1] for d in doc_data)
    assert stats.total_documents_public == doc_data[0][1]
    assert stats.total_documents_organization == doc_data[1][1]
    assert stats.total_documents_private == doc_data[2][1]
    assert stats.total_documents_invisible == doc_data[3][1]
    assert stats.total_pages == sum(d[1] * d[2] for d in doc_data)
    assert stats.total_pages_public == doc_data[0][1] * doc_data[0][2]
    assert stats.total_pages_organization == doc_data[1][1] * doc_data[1][2]
    assert stats.total_pages_private == doc_data[2][1] * doc_data[2][2]
    assert stats.total_pages_invisible == doc_data[3][1] * doc_data[3][2]
    assert stats.total_notes == sum(n[1] for n in note_data)
    assert stats.total_notes_public == note_data[0][1]
    assert stats.total_notes_organization == note_data[1][1]
    assert stats.total_notes_private == note_data[2][1]
    assert stats.total_notes_invisible == note_data[3][1]
    assert stats.total_projects == num_projects
