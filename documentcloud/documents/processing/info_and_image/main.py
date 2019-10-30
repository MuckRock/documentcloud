# Standard Library
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
from listcrunch import crunch
from PIL import Image

env = environ.Env()

if env.str("ENVIRONMENT").startswith("local"):
    # Load from Django imports if in a local environment
    from documentcloud.documents.processing.info_and_image.pdfium import (
        StorageHandler,
        Workspace,
    )
    from documentcloud.documents.processing.info_and_image.environment import (
        publisher,
        storage,
        get_http_data,
        get_pubsub_data,
    )
else:
    # Otherwise, load directly as a package to be compatible with cloud functions
    from pdfium import StorageHandler, Workspace
    from environment import publisher, storage, get_http_data, get_pubsub_data

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


redis_url = furl.furl(env.str("REDIS_PROCESSING_URL"))
redis = redis.Redis(host=redis_url.host, port=redis_url.port, db=0)
bucket = env.str("DOCUMENT_BUCKET", default="")


# Topic names for the messaging queue
image_extract_topic = publisher.topic_path(
    "documentcloud",
    env.str("IMAGE_EXTRACT_TOPIC", default="page-image-ready-for-extraction"),
)
ocr_topic = publisher.topic_path(
    "documentcloud", env.str("OCR_TOPIC", default="ocr-queue")
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


def write_cache_and_pagesizes(path):
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
        page_sizes = []
        pagespecs = []
        doc.load_page(page_count - 1)
        for i in range(page_count):
            page = doc.load_page(i)
            page_sizes.append(page.height / page.width)
            pagespecs.append(f"{page.width}x{page.height}")
        with storage.open(get_pagesize_path(path), "w") as pagesize_file:
            pagesize_file.write(crunch(pagespecs))
        cached = pdf_file.cache

    # Create an index file that stores the memory locations of each page of the
    # PDF file.
    index_path = get_index_path(path)
    with storage.open(index_path, "wb") as pickle_file, gzip.open(
        pickle_file, "wb"
    ) as zip_file:
        pickle.dump(cached, zip_file)

    # Pass the page_count back to the caller.
    return page_count, page_sizes


def process_pdf(request, _context=None):
    """Process a PDF file's information and launch extraction tasks."""
    data = get_http_data(request)

    # Ensure a PDF file
    path = os.path.join(bucket, data["path"])
    if not path.endswith(DOCUMENT_SUFFIX):
        return "not a pdf"

    page_count, page_sizes = write_cache_and_pagesizes(path)

    # Store the page count in redis
    redis.hset(get_id(path), "image", page_count)
    redis.hset(get_id(path), "text", page_count)

    # Send update
    page_spec = crunch(page_sizes)  # Compress the spec of each page's dimensions

    requests.patch(
        urljoin(env.str("API_CALLBACK"), f"documents/{get_id(path)}/"),
        json={"page_count": page_count, "page_spec": page_spec},
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

    return get_pageimage_path(original_path, page_number, IMAGE_WIDTHS[0][0])


def extract_image(data, _context=None):
    """Renders (extracts) an image from a PDF file."""
    data = get_pubsub_data(data)

    path = os.path.join(bucket, data["path"])  # The PDF file path
    page_numbers = data["pages"]  # The page numbers to extract
    index_path = get_index_path(path)  # The path to the PDF index file

    # Store a queue of pages to OCR to fill the batch
    ocr_queue = []

    def flush(ocr_queue):
        if not ocr_queue:
            return

        # Trigger ocr pipeline
        publisher.publish(
            ocr_topic,
            data=json.dumps({"paths": [page[1] for page in ocr_queue]}).encode("utf8"),
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

    with Workspace() as workspace, StorageHandler(
        storage, path, record=False, playback=True, cache=cached
    ) as pdf_file, workspace.load_document_custom(pdf_file) as doc:
        for page_number in page_numbers:
            # Extract the image.
            large_image_path = extract_single_page(data["path"], path, doc, page_number)

            images_remaining = redis.hincrby(get_id(path), "image", -1)

            # Prepare the image to be OCRd.
            ocr_queue.append([page_number, large_image_path])
            check_and_flush(ocr_queue)

    flush(ocr_queue)

    return "Ok"
