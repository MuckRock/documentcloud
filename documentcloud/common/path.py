"""
Helper functions to standardize the paths where files associated with a document are
stored
"""

# Third Party
import environ

env = environ.Env()
DOCUMENT_BUCKET = env.str("DOCUMENT_BUCKET")

DOCUMENT_SUFFIX = "pdf"
INDEX_SUFFIX = "index"
PAGESIZE_SUFFIX = "pagesize"
IMAGE_SUFFIX = "gif"
TEXT_SUFFIX = "txt"
SELECTABLE_TEXT_SUFFIX = "position.json"
JSON_TEXT_SUFFIX = "txt.json"


def temp(doc_id):
    return f"_{doc_id}"


def path(doc_id):
    """The path where this document's files are located"""
    return f"{DOCUMENT_BUCKET}/documents/{doc_id}/"


def file_path(doc_id, slug, ext):
    """The path to one of the files associated with this document"""
    return path(doc_id) + f"{slug}.{ext}"


def doc_path(doc_id, slug):
    """The path to the document file"""
    return file_path(doc_id, slug, DOCUMENT_SUFFIX)


def doc_revision_path(doc_id, slug, version, extension):
    """The path to the document file"""
    return path(doc_id) + f"revisions/{version:04d}-{slug}.{extension}"


def original_path(doc_id, slug, extension):
    """The path to the original file before converting to PDF"""
    return path(doc_id) + "original/" + f"{slug}.{extension}"


def index_path(doc_id, slug):
    """The path to the index file"""
    return file_path(doc_id, slug, INDEX_SUFFIX)


def pagesize_path(doc_id, slug):
    """The path to the pagesize file"""
    return file_path(doc_id, slug, PAGESIZE_SUFFIX)


def text_path(doc_id, slug):
    """The path to the text file"""
    return file_path(doc_id, slug, TEXT_SUFFIX)


def json_text_path(doc_id, slug):
    """The path to the json text file"""
    return file_path(doc_id, slug, JSON_TEXT_SUFFIX)


def pages_path(doc_id):
    """The path to the pages directory for this document"""
    return path(doc_id) + "pages/"


def page_image_path(doc_id, slug, page_number, page_size):
    """The path to the image file for a single page"""
    return pages_path(doc_id) + f"{slug}-p{page_number + 1}-{page_size}.{IMAGE_SUFFIX}"


def page_text_path(doc_id, slug, page_number):
    """The path to the text file for a single page"""
    return pages_path(doc_id) + f"{slug}-p{page_number + 1}.{TEXT_SUFFIX}"


def page_text_position_path(doc_id, slug, page_number):
    """The path to the text file for a single page"""
    return pages_path(doc_id) + f"{slug}-p{page_number + 1}.{SELECTABLE_TEXT_SUFFIX}"


def sidekick_path(proj_id):
    """The path where this projects's sidekick files are located"""
    return f"{DOCUMENT_BUCKET}/sidekick/{proj_id}/"


def sidekick_document_vectors_path(proj_id):
    """The path where this projects's sidekick files are located"""
    return f"{DOCUMENT_BUCKET}/sidekick/{proj_id}/doc_vectors.npz"


def import_org_csv(org_id):
    import_dir = env.str("IMPORT_DIR")
    import_bucket = env.str("IMPORT_BUCKET")
    return f"{import_bucket}/{import_dir}/organization-{org_id}/documents.csv"


def import_org_pagespec_csv(org_id):
    """The path to the documents CSV for a given org post-import on lambda"""
    import_dir = env.str("IMPORT_DIR")
    import_bucket = env.str("IMPORT_BUCKET")
    return f"{import_bucket}/{import_dir}/organization-{org_id}/documents.pagespec.csv"
