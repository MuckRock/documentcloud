from documentcloud.documents.processing.info_and_image.pdfium import Workspace

original_file = "documentcloud/documents/processing/tests/pdfs/doc_3.pdf"
text_overlay_file = "documentcloud/documents/processing/tests/pdfs/output_test6.pdf"

# Resize text overlay doc
with Workspace() as workspace:
    # Get desired dimensions
    original_doc = workspace.load_document(original_file)
    original_page = original_doc.load_page(0)
    original_width, original_height = original_page.width, original_page.height
    print("original dimensions", original_width, "x", original_height)

    text_doc = workspace.load_document(text_overlay_file)
    text_page = text_doc.load_page(0)
    text_width, text_height = text_page.width, text_page.height
    print("text dimensions", text_width, "x", text_height)
