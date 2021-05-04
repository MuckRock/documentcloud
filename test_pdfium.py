TEXT_OBJECT = 1
from ctypes import c_float, byref
import shutil, os, time
from documentcloud.documents.processing.info_and_image.pdfium import Workspace, Matrix
from documentcloud.common.environment.local.storage import storage

with Workspace() as workspace:
    doc = workspace.load_document(
        "documentcloud/documents/processing/tests/pdfs/output_test6.pdf"
    )

    shutil.copyfile(
        "documentcloud/documents/processing/tests/pdfs/doc_3.pdf",
        "documentcloud/documents/processing/tests/pdfs/doc_3_modified.pdf",
    )
    original_doc = workspace.load_document(
        "documentcloud/documents/processing/tests/pdfs/doc_3_modified.pdf"
    )
    original_page = original_doc.load_page(0)
    new_doc = workspace.new_document()
    new_doc.import_pages(original_doc, f"1", 0)
    new_doc.import_pages(doc, f"1", 1)
    # new_page = new_doc.add_page(page.width, page.height)
    new_page = new_doc.load_page(0)
    page = new_doc.load_page(1)

    # tess_dimensions = page.width, page.height
    # page_dimensions = new_page.width, new_page.height
    x_scale = new_page.width / page.width
    y_scale = new_page.height / page.height

    num_objects = workspace.fpdf_count_objects(page.page)
    j = 0
    for i in range(num_objects):
        page_object = workspace.fpdf_get_object(page.page, j)
        if workspace.fpdf_object_get_type(page_object) != TEXT_OBJECT:
            j += 1
            continue
        print(
            "PLACING TEXT OBJECT",
            workspace.fpdf_object_get_type(page_object),
            page.get_bounds(page_object),
        )

        # Scale
        workspace.fpdf_page_obj_transform(page_object, x_scale, 0, 0, y_scale, 0, 0)

        # matrix = Matrix()
        # workspace.fpdf_get_text_matrix(page_object, matrix.ref())
        # matrix.scale(x_scale, y_scale)
        # print(matrix.list)

        assert workspace.fpdf_remove_object(page.page, page_object) == 1
        workspace.fpdf_insert_object(new_page.page, page_object)
    new_doc.remove_page(1)
    page.save()
    new_page.save()
    # workspace.fpdf_close_page(new_page.page)
    generated_path = f"documentcloud/documents/processing/tests/pdfs/doc_3_overlaid_{round(time.time())}.pdf"
    new_doc.save(storage, os.path.abspath(generated_path), None)
    print(generated_path)

