"""
Helper functions to standardize the name of the fields used to store data in Redis
"""


def images_remaining(doc_id):
    return f"{doc_id}:image"


def texts_remaining(doc_id):
    return f"{doc_id}:text"


def page_count(doc_id):
    return f"{doc_id}:pages"


def dimensions(doc_id):
    return f"{doc_id}:dimensions"


def page_dimension(doc_id, page_dimension):
    return f"{doc_id}:dim{page_dimension}"


def page_text(doc_id):
    return f"{doc_id}:pagetext"


def is_running(doc_id):
    return f"{doc_id}:running"


def image_bits(doc_id):
    return f"{doc_id}:imageBits"


def text_bits(doc_id):
    return f"{doc_id}:textBits"
