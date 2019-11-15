# Standard Library
import collections
import gzip
import json
import os
import pickle
from urllib.parse import urljoin

# Third Party
import environ
import furl
import redis
import requests
from listcrunch import crunch_collection
from PIL import Image

env = environ.Env()

if env.bool("SERVERLESS"):
    # Load directly as a package to be compatible with cloud functions
    from pdfium import StorageHandler, Workspace
    from environment import (
        publisher,
        storage,
        get_http_data,
        get_pubsub_data,
        RedisFields,
    )
else:
    # Load from Django imports if in a Django context
    from documentcloud.documents.processing.info_and_image.pdfium import (
        StorageHandler,
        Workspace,
    )
    from documentcloud.documents.processing.info_and_image.environment import (
        publisher,
        storage,
        get_http_data,
        get_pubsub_data,
        RedisFields,
    )

DOCUMENT_SUFFIX = ".pdf"
INDEX_SUFFIX = ".index"
PAGESIZE_SUFFIX = ".pagesize"
IMAGE_SUFFIX = ".gif"
IMAGE_BATCH = env.int(
    "EXTRACT_IMAGE_BATCH", default=55
)  # Number of images to extract with each function
OCR_BATCH = env.int("OCR_BATCH", 1)  # Number of pages to OCR with each function


def parse_extract_width(width_str):
    extract_width = width_str.split(":")
    return [extract_width[0], int(extract_width[1])]


IMAGE_WIDTHS = [
    parse_extract_width(x)
    for x in env.list(
        "IMAGE_EXTRACT_WIDTHS",
        default=["large:1000", "normal:700", "small:180", "thumbnail:60"],
    )
]  # width of images to OCR

REDIS_URL = furl.furl(env.str("REDIS_PROCESSING_URL"))
REDIS_PASSWORD = env.str("REDIS_PROCESSING_PASSWORD")
REDIS = redis.Redis(
    host=REDIS_URL.host, port=REDIS_URL.port, password=REDIS_PASSWORD, db=0
)
DOCUMENT_BUCKET = env.str("DOCUMENT_BUCKET", default="")

# Topic names for the messaging queue
pdf_process_topic = publisher.topic_path(
    "documentcloud", env.str("PDF_PROCESS_TOPIC", default="pdf-process")
)
image_extract_topic = publisher.topic_path(
    "documentcloud", env.str("IMAGE_EXTRACT_TOPIC", default="image-extraction")
)
ocr_topic = publisher.topic_path(
    "documentcloud", env.str("OCR_TOPIC", default="ocr-extraction")
)


def get_index_path(path):
    """Returns the PDF index file corresponding with its file name"""
    assert path.endswith(DOCUMENT_SUFFIX)
    return path[: -len(DOCUMENT_SUFFIX)] + INDEX_SUFFIX


def get_pagesize_path(path):
    """Returns the PDF page size file corresponding with its file name"""
    assert path.endswith(DOCUMENT_SUFFIX)
    return path[: -len(DOCUMENT_SUFFIX)] + PAGESIZE_SUFFIX


def get_pageimage_path(pdf_path, page_number, page_suffix):
    """Returns the appropriate PDF page image path."""
    assert pdf_path.endswith(DOCUMENT_SUFFIX)
    slug = os.path.basename(pdf_path)[: -len(DOCUMENT_SUFFIX)]
    page_dir = os.path.join(os.path.dirname(pdf_path), "pages")
    return os.path.join(
        page_dir, f"{slug}-p{page_number + 1}-{page_suffix}{IMAGE_SUFFIX}"
    )


def get_id(pdf_path):
    """Returns the document ID associated with the PDF file path."""
    return pdf_path.split("/")[-2]


def initialize_redis_page_data(doc_id, page_count):
    dimensions_field = RedisFields.dimensions(doc_id)
    image_bits_field = RedisFields.image_bits(doc_id)
    text_bits_field = RedisFields.text_bits(doc_id)

    def dimensions_field_update(pipeline):
        existing_dimensions = pipeline.get(dimensions_field)

        # Put the pipeline back in multi mode
        pipeline.multi()

        # Set the page count field
        pipeline.set(RedisFields.page_count(doc_id), page_count)

        # Set pages and texts remaining to page count
        pipeline.set(RedisFields.images_remaining(doc_id), page_count)
        pipeline.set(RedisFields.texts_remaining(doc_id), page_count)

        # Set Redis bit arrays flooded to 0 to track each page
        pipeline.delete(image_bits_field)
        pipeline.delete(text_bits_field)
        pipeline.setbit(image_bits_field, page_count - 1, 0)
        pipeline.setbit(text_bits_field, page_count - 1, 0)

        # Remove any existing dimensions that may be lingering
        if existing_dimensions is not None:
            for dimension in existing_dimensions:
                pipeline.delete(RedisFields.page_dimension(doc_id, dimension))
        pipeline.delete(dimensions_field)

    # Ensure atomicity while getting a value with the transaction wrapper around WATCH
    # See https://pypi.org/project/redis/#pipelines for details
    REDIS.transaction(dimensions_field_update, dimensions_field)


def extract_pagecount(path):
    """Parse a PDF and write files to cache PDF information and dimensions.

    Returns:
        A tuple containing the number of pages in the PDF file and an array of
        page sizes.
    """
    # Get the page sizes and initialize a cache of page positions
    with Workspace() as workspace, StorageHandler(
        storage, path, record=True
    ) as pdf_file, workspace.load_document_custom(pdf_file) as doc:
        page_count = doc.page_count
        cached = pdf_file.cache

    # Create an index file that stores the memory locations of each page of the
    # PDF file.
    index_path = get_index_path(path)
    with storage.open(index_path, "wb") as pickle_file, gzip.open(
        pickle_file, "wb"
    ) as zip_file:
        pickle.dump(cached, zip_file)

    # Pass the page_count back to the caller.
    return page_count


def get_redis_pagespec(doc_id):
    dimensions_field = RedisFields.dimensions(doc_id)

    pipeline = REDIS.pipeline()

    # We cannot use the convenience transacation wrapper since values we watch are dynamic
    # See https://pypi.org/project/redis/#pipelines for details
    while True:
        try:
            # Start collecting page specs (resets if there's a watch error)
            pagespec = collections.defaultdict(list)

            pipeline.watch(dimensions_field)
            # Restart if the dimensions are altered during runtime
            page_dimensions = pipeline.smembers(dimensions_field)
            if page_dimensions is None:
                # If there are no page dimensions, exit with empty pagespec
                pipeline.execute()
                break

            for page_dimension in page_dimensions:
                page_dimension = page_dimension.decode("utf8")
                page_dimension_field = RedisFields.page_dimension(
                    doc_id, page_dimension
                )
                # Restart if any page dimension is altered during runtime
                pipeline.watch(page_dimension_field)
                page_numbers = pipeline.smembers(page_dimension_field)
                if page_numbers is not None:
                    for page_number in page_numbers:
                        page_number = int(page_number.decode("utf8"))
                        # Set the pagespec for each page number and dimension
                        pagespec[page_dimension].append(page_number)

            # Run the pipeline
            pipeline.execute()
            break
        except WatchError:
            continue
        finally:
            pipeline.reset()

    return pagespec


def write_pagespec(path, doc_id):
    pagespec = get_redis_pagespec(doc_id)
    crunched_pagespec = crunch_collection(pagespec)
    with storage.open(get_pagesize_path(path), "w") as pagesize_file:
        pagesize_file.write(crunched_pagespec)

    # Send pagespec update
    requests.patch(
        urljoin(env.str("API_CALLBACK"), f"documents/{doc_id}/"),
        json={"page_spec": crunched_pagespec},
        headers={"Authorization": f"processing-token {env.str('PROCESSING_TOKEN')}"},
    )


def process_pdf(request, _context=None):
    """Process a PDF file's information and launch extraction tasks."""
    data = get_http_data(request)

    # Launch PDF processing via pubsub
    publisher.publish(pdf_process_topic, data=json.dumps(data).encode("utf8"))

    return "Ok"


def process_pdf_internal(data, _context=None):
    """Process a PDF file's information and launch extraction tasks."""
    data = get_pubsub_data(data)

    # Ensure a PDF file
    path = os.path.join(DOCUMENT_BUCKET, data["path"])
    if not path.endswith(DOCUMENT_SUFFIX):
        return "not a pdf"

    page_count = extract_pagecount(path)

    # Store the page count in redis
    doc_id = get_id(path)

    initialize_redis_page_data(doc_id, page_count)

    requests.patch(
        urljoin(env.str("API_CALLBACK"), f"documents/{get_id(path)}/"),
        json={"page_count": page_count},
        headers={"Authorization": f"processing-token {env.str('PROCESSING_TOKEN')}"},
    )

    # Kick off image processing tasks
    for i in range(0, page_count, IMAGE_BATCH):
        # Trigger image extraction for each page
        pages = list(range(i, min(i + IMAGE_BATCH, page_count)))
        publisher.publish(
            image_extract_topic,
            data=json.dumps({"path": data["path"], "pages": pages}).encode("utf8"),
        )

    return "Ok"


def extract_single_page(original_path, path, doc, page_number):
    """Internal method to extract a single page from a PDF file as an image.

    Returns:
        The path to the newly rendered large image path.
    """
    # Load the page from the PDF
    page = doc.load_page(page_number)
    large_image_path = get_pageimage_path(path, page_number, IMAGE_WIDTHS[0][0])

    # Extract the page as an image with a certain width
    bmp = page.get_bitmap(IMAGE_WIDTHS[0][1], None)
    img_buffer = bmp.render(storage, large_image_path)

    # Resize to render smaller page sizes
    for [image_suffix, image_width] in IMAGE_WIDTHS[1:]:
        img = img_buffer.resize(
            (image_width, round(img_buffer.height * (image_width / img_buffer.width))),
            Image.ANTIALIAS,
        )
        with storage.open(
            get_pageimage_path(path, page_number, image_suffix), "wb"
        ) as img_f:
            img.save(img_f, format=IMAGE_SUFFIX[1:].lower())

        # TODO: trigger update when thumbnail image is parsed

    return (
        get_pageimage_path(original_path, page_number, IMAGE_WIDTHS[0][0]),
        page.width,
        page.height,
    )


def extract_image(data, _context=None):
    """Renders (extracts) an image from a PDF file."""
    data = get_pubsub_data(data)

    path = os.path.join(DOCUMENT_BUCKET, data["path"])  # The PDF file path
    page_numbers = data["pages"]  # The page numbers to extract
    index_path = get_index_path(path)  # The path to the PDF index file

    # Store a queue of pages to OCR to fill the batch
    ocr_queue = []

    def flush(ocr_queue):
        if not ocr_queue:
            return

        # Trigger ocr pipeline
        publisher.publish(
            ocr_topic, data=json.dumps({"paths_and_numbers": ocr_queue}).encode("utf8")
        )

        ocr_queue.clear()

    def check_and_flush(ocr_queue):
        if len(ocr_queue) >= OCR_BATCH:
            flush(ocr_queue)

    # Open the PDF file with the cached index
    with storage.open(index_path, "rb") as pickle_file, gzip.open(
        pickle_file, "rb"
    ) as zip_file:
        cached = pickle.load(zip_file)

    doc_id = get_id(path)
    images_remaining_field = RedisFields.images_remaining(doc_id)
    image_bits_field = RedisFields.image_bits(doc_id)
    with Workspace() as workspace, StorageHandler(
        storage, path, record=False, playback=True, cache=cached
    ) as pdf_file, workspace.load_document_custom(pdf_file) as doc:
        for page_number in page_numbers:
            # Only process if it has not processed previously
            if REDIS.getbit(image_bits_field, page_number) == 0:
                # Extract the image.
                large_image_path, width, height = extract_single_page(
                    data["path"], path, doc, page_number
                )
                page_dimension = f"{width}x{height}"

                # Update Redis properties atomically
                pipeline = REDIS.pipeline()

                # Update the page dimensions in Redis
                pipeline.sadd(RedisFields.dimensions(doc_id), page_dimension)
                pipeline.sadd(
                    RedisFields.page_dimension(doc_id, page_dimension), page_number
                )
                # Decrement pages remaining and set the bit for the page off in Redis
                pipeline.decr(images_remaining_field)
                pipeline.setbit(image_bits_field, page_number, 1)
                images_remaining = pipeline.execute()[2]

                if images_remaining == 0:
                    write_pagespec(path, doc_id)

            # Prepare the image to be OCRd.
            ocr_queue.append([page_number, large_image_path])
            check_and_flush(ocr_queue)

    flush(ocr_queue)

    return "Ok"
