def images_remaining(doc_id):
    return f"{doc_id}:image"


def texts_remaining(doc_id):
    return f"{doc_id}:text"


def page_count(doc_id):
    return f"{doc_id}:pages"


def dimensions(doc_id):
    return f"{doc_id}:dimensions"


def page_dimension(doc_id, page_dimension_):
    return f"{doc_id}:dim{page_dimension_}"


def image_bits(doc_id):
    return f"{doc_id}:imageBits"


def text_bits(doc_id):
    return f"{doc_id}:textBits"
