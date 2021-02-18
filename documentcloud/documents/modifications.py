# Standard Library
from collections import defaultdict
from copy import copy

# DocumentCloud
from documentcloud.documents.models import Document, Note, Section

ANGLE_TABLE = {"": 0, "cc": 1, "hw": 2, "cw": 3}


def iterate_page_spec(page_spec):
    for spec in page_spec:
        if isinstance(spec, list):
            # Page range
            yield from range(spec[0], spec[1] + 1)
        else:
            # Individual page
            yield spec


def post_process(document, modifications):
    """Post process the notes and sections for the document as specified by
    modifications
    """

    # (document.id, old_page) -> [(new_page, rotation), ...]
    page_map = _build_page_map(document, modifications)

    # load all documents, notes and sections
    # prefetch all notes and sections
    documents = Document.objects.prefetch_related("notes", "sections").filter(
        id__in=[doc_id for doc_id, _page in page_map]
    )

    def remove_note(note, updates, _deletes):
        """Removed notes are detached to page notes on the first page"""
        note.detach()
        updates.append(note)

    def remove_section(section, _updates, deletes):
        """Removed sections are deleted"""
        deletes.append(section)

    # map all notes and sections from involved documents to their correct places
    # the first occurence of a note or section from the original document may be
    # moved instead of copied
    for source_document in documents:
        create_notes, update_notes, delete_notes = _process_page_objs(
            page_map,
            document,
            source_document,
            source_document.notes.all(),
            remove_note,
        )

        create_sections, update_sections, delete_sections = _process_page_objs(
            page_map,
            document,
            source_document,
            source_document.sections.all(),
            remove_section,
        )

    _commit_db(Note, create_notes, update_notes, delete_notes)
    _commit_db(Section, create_sections, update_sections, delete_sections)


def _build_page_map(document, modifications):
    """The page map is a dictionary mapping the source document id and  page number to a
    list of the new page numbers in the modified document and the rotation
    """
    # (document.id, old_page) -> [(new_page, rotation), ...]
    page_map = defaultdict(list)
    page_number = 0

    # build a map from original page to new page(s)
    for modification in modifications:
        doc_id = modification.get("id", document.pk)
        page_spec = modification["page_spec"]
        modifiers = modification.get("modifications", [])
        for old_page in iterate_page_spec(page_spec):

            rotation = 0
            for modifier in modifiers:
                # XXX there should never be more than 1 rotation
                rotation += ANGLE_TABLE.get(modifier.get("angle", ""), 0)

            page_map[(doc_id, old_page)].append((page_number, rotation))

            page_number += 1

    document.page_count = page_number
    document.save()

    return page_map


def _process_page_objs(page_map, original_document, source_document, objects, remove):
    """Move or copy the objects from the source document to their new pages
    in the modified document
    """

    creates = []
    updates = []
    deletes = []

    for obj in objects:
        new_pages = page_map.get((source_document.id, obj.page_number))
        if new_pages:
            if source_document == original_document:
                # if this is the original document, we can move the first instance
                # of this object instead of copying it
                new_page, rotation = new_pages[0]
                new_pages = new_pages[1:]
                if hasattr(obj, "rotate"):
                    obj.rotate(rotation)
                obj.page_number = new_page
                updates.append(obj)
            for new_page, rotation in new_pages:
                new_obj = copy(obj)
                new_obj.id = None
                new_obj.document = original_document
                new_obj.page_number = new_page
                if hasattr(obj, "rotate"):
                    new_obj.rotate(rotation)
                creates.append(new_obj)
        elif source_document == original_document:
            # handle an objects page being removed from the original document
            remove(obj, updates, deletes)

    return creates, updates, deletes


def _commit_db(model, creates, updates, deletes):
    """Commit object changes to the database in bulk to minimize SQL calls"""
    if creates:
        model.objects.bulk_create(creates)
    if updates:
        model.objects.bulk_update(updates)
    if deletes:
        model.objects.filter(id__in=[i.id for i in deletes]).delete()


"""
Test cases:
    - insert page before/after note/section
    - remove page before/after note/section
    - duplicate page with note/section
    - remove page with note/section
    - rotate page with note/section
    - copy page from another document with a note/section
    - complex text combining many modifications
"""
