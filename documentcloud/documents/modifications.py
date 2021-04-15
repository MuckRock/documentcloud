# Standard Library
# Django
from django.db import transaction

from collections import defaultdict
from copy import copy

# DocumentCloud
from documentcloud.documents.choices import Status
from documentcloud.documents.models import Document, Note, Section

ANGLE_TABLE = {"": 0, "cc": 1, "hw": 2, "ccw": 3}


def iterate_page_spec(page_spec):
    for spec in page_spec:
        if isinstance(spec, list):
            # Page range
            yield from range(spec[0], spec[1] + 1)
        else:
            # Individual page
            yield spec


def remove_note(note, updates, _deletes):
    """Removed notes are detached to page notes on the first page"""
    note.detach()
    updates.append(note)


def remove_section(section, _updates, deletes):
    """Removed sections are deleted"""
    deletes.append(section)


@transaction.atomic
def post_process(document, modifications):
    """Post process the notes and sections for the document as specified by
    modifications
    """
    from documentcloud.documents.tasks import solr_index

    # Remove entities (no matter what)
    document.entities.all().delete()

    # (document.id, old_page) -> [(new_page, rotation), ...]
    page_map = _build_page_map(document, modifications)

    # load all documents, notes and sections
    # prefetch all notes and sections
    documents = Document.objects.prefetch_related("notes", "sections").filter(
        id__in=[doc_id for doc_id, _page in page_map]
    )

    # map all notes and sections from involved documents to their correct places
    # the first occurence of a note or section from the original document may be
    # moved instead of copied
    create_notes, update_notes, delete_notes = [], [], []
    create_sections, update_sections, delete_sections = [], [], []
    for source_document in documents:
        creates, updates, deletes = _process_page_objs(
            page_map,
            document,
            source_document,
            source_document.notes.all(),
            remove_note,
        )
        create_notes.extend(creates)
        update_notes.extend(updates)
        delete_notes.extend(deletes)

        creates, updates, deletes = _process_page_objs(
            page_map,
            document,
            source_document,
            source_document.sections.all(),
            remove_section,
        )
        create_sections.extend(creates)
        update_sections.extend(updates)
        delete_sections.extend(deletes)

    _commit_db(
        Note,
        ["page_number", "x1", "y1", "x2", "y2"],
        create_notes,
        update_notes,
        delete_notes,
    )
    _commit_db(
        Section, ["page_number"], create_sections, update_sections, delete_sections
    )

    document.status = Status.success
    document.save()

    transaction.on_commit(
        lambda: solr_index.delay(
            document.pk, field_updates={"status": "set", "page_count": "set"}
        )
    )


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
                rotation += ANGLE_TABLE.get(modifier.get("angle", ""), 0)

            page_map[(doc_id, old_page)].append((page_number, rotation))

            page_number += 1

    document.page_count = page_number

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
                # we take the first instance off here, but do not process it yet
                # if we need to rotate it, we do not want it to be double
                # rotated if it is also copied
                move_new_page, move_rotation = new_pages[0]
                new_pages = new_pages[1:]
            for new_page, rotation in new_pages:
                new_obj = copy(obj)
                new_obj.id = None
                new_obj.document = original_document
                new_obj.page_number = new_page
                if hasattr(new_obj, "rotate"):
                    new_obj.rotate(rotation)
                creates.append(new_obj)
            if source_document == original_document:
                # if this is the original document, we can move the first instance
                # of this object instead of copying it
                # process it here after we have made any necessary copies
                if hasattr(obj, "rotate"):
                    obj.rotate(move_rotation)
                obj.page_number = move_new_page
                updates.append(obj)
        elif source_document == original_document:
            # handle an objects page being removed from the original document
            remove(obj, updates, deletes)

    return creates, updates, deletes


def _commit_db(model, fields, creates, updates, deletes):
    """Commit object changes to the database in bulk to minimize SQL calls"""
    if deletes:
        model.objects.filter(id__in=[i.id for i in deletes]).delete()
    if updates:
        model.objects.bulk_update(updates, fields)
    if creates:
        model.objects.bulk_create(creates)
