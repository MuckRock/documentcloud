"""
Helper functions to standardize the name of the fields used to store data in Redis
"""


def images_remaining(doc_id):
    return f"{doc_id}:image"


def texts_remaining(doc_id):
    return f"{doc_id}:text"


def text_positions_remaining(doc_id):
    return f"{doc_id}:textposition"


def page_count(doc_id):
    return f"{doc_id}:pages"


def dimensions(doc_id):
    return f"{doc_id}:dimensions"


def page_dimension(doc_id, page_dimension_):
    return f"{doc_id}:dim{page_dimension_}"


def page_text(doc_id):
    return f"{doc_id}:pagetext"


def page_text_pdf(doc_id):
    return f"{doc_id}:pagetextpdf"


def is_running(doc_id):
    return f"{doc_id}:running"


def image_bits(doc_id):
    return f"{doc_id}:imageBits"


def text_bits(doc_id):
    return f"{doc_id}:textBits"


def text_position_bits(doc_id):
    return f"{doc_id}:textpositionBits"


def file_hash(doc_id):
    return f"{doc_id}:fileHash"


def import_pagespecs(org_id):
    return f"{org_id}:pagespec"


def import_docs_remaining(org_id):
    return f"{org_id}:docsRemaining"
