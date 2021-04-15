# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.models import Section
from documentcloud.documents.modifications import post_process
from documentcloud.documents.tests.factories import (
    DocumentFactory,
    NoteFactory,
    SectionFactory,
)

models = [(NoteFactory, "notes"), (SectionFactory, "sections")]
tests = [
    ([0, [0, 2]], 1, 2, 1, 4),  # insert page before, moves back a page
    ([[0, 2], 2], 1, 1, 1, 4),  # insert page after, does not move
    ([[1, 2]], 1, 0, 1, 2),  # remove page before, move forward a page
    ([[0, 1]], 1, 1, 1, 2),  # remove page after, does not move
    ([1, [0, 2]], 1, 0, 2, 4),  # duplicate page with obj, now 2 objects
]


@pytest.mark.django_db()
class TestPostProcess:
    """Test the page modification post processing"""

    # pylint: disable=too-many-arguments
    @pytest.mark.parametrize("factory,attr", models)
    @pytest.mark.parametrize(
        "page_spec,initial_page,final_page,count,page_count", tests
    )
    def test_simple(
        self, factory, attr, page_spec, initial_page, final_page, count, page_count
    ):
        """Test simple modifications"""
        document = DocumentFactory(page_count=3)
        obj = factory.create(document=document, page_number=initial_page)
        modifications = [{"page_spec": page_spec}]
        post_process(document, modifications)
        assert getattr(document, attr).count() == count
        obj.refresh_from_db()
        assert obj.page_number == final_page
        document.refresh_from_db()
        assert document.page_count == page_count

    def test_remove_note(self):
        """Test removing the page with a note"""
        document = DocumentFactory(page_count=3)
        note = NoteFactory.create(document=document, page_number=1)
        modifications = [{"page_spec": [0, 2]}]
        post_process(document, modifications)
        # the note is moved to the first page as a page note
        assert document.notes.count() == 1
        note.refresh_from_db()
        # moved to the first page
        assert note.page_number == 0
        # as a full page note
        assert note.x1 is None
        document.refresh_from_db()
        assert document.page_count == 2

    def test_remove_section(self):
        """Test removing the page with a section"""
        document = DocumentFactory(page_count=3)
        section = SectionFactory.create(document=document, page_number=1)
        modifications = [{"page_spec": [0, 2]}]
        post_process(document, modifications)
        # the section is deleted
        assert document.sections.count() == 0
        with pytest.raises(Section.DoesNotExist):
            section.refresh_from_db()
        document.refresh_from_db()
        assert document.page_count == 2

    def test_rotate_note(self):
        """Test rotating the page with a note"""
        document = DocumentFactory(page_count=3)
        note = NoteFactory.create(document=document, page_number=1)
        x1, x2, y1, y2 = note.x1, note.x2, note.y1, note.y2
        assert None not in (x1, x2, y1, y2)
        modifications = [
            {
                "page_spec": [[0, 2]],
                "modifications": [{"type": "rotate", "angle": "cc"}],
            }
        ]
        post_process(document, modifications)
        # still one note
        assert document.notes.count() == 1
        note.refresh_from_db()
        # not moved
        assert note.page_number == 1
        # but is rotated
        assert (
            note.x1 == (1 - y2)
            and note.x2 == (1 - y1)
            and note.y1 == x1
            and note.y2 == x2
        )
        document.refresh_from_db()
        assert document.page_count == 3

    def test_rotate_section(self):
        """Test rotating the page with a section"""
        document = DocumentFactory(page_count=3)
        section = SectionFactory.create(document=document, page_number=1)
        modifications = [
            {
                "page_spec": [[0, 2]],
                "modifications": [{"type": "rotate", "angle": "ccw"}],
            }
        ]
        post_process(document, modifications)
        # still one section
        assert document.sections.count() == 1
        section.refresh_from_db()
        # not moved
        assert section.page_number == 1
        document.refresh_from_db()
        assert document.page_count == 3

    @pytest.mark.parametrize("factory,attr", models)
    def test_import(self, factory, attr):
        """Test importing a page with a note"""
        document = DocumentFactory(page_count=3)
        import_document = DocumentFactory(page_count=1)
        obj = factory.create(document=import_document, page_number=0)
        modifications = [
            {"page_spec": [[0, 2]]},
            {"id": import_document.pk, "page_spec": [0]},
        ]
        post_process(document, modifications)
        # both document and import document have one obj now
        assert getattr(document, attr).count() == 1
        assert getattr(import_document, attr).count() == 1
        obj.refresh_from_db()
        # not moved
        assert obj.page_number == 0
        assert obj.document == import_document
        # new obj
        new_obj = getattr(document, attr).first()
        assert new_obj.page_number == 3
        assert new_obj.document == document
        document.refresh_from_db()
        assert document.page_count == 4

    def test_section_delete_and_move(self):
        """Test deleting and moving sections obeys unique constraint
        This can be avoided by deleting, then updating, then creating
        """
        document = DocumentFactory(page_count=3)
        section1 = SectionFactory.create(document=document, page_number=1)
        section2 = SectionFactory.create(document=document, page_number=2)
        modifications = [{"page_spec": [2, 2, 2]}]
        post_process(document, modifications)
        assert document.sections.count() == 3
        with pytest.raises(Section.DoesNotExist):
            section1.refresh_from_db()
        section2.refresh_from_db()
        assert section2.page_number == 0
        document.refresh_from_db()
        assert document.page_count == 3
