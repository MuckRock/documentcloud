# Standard Library
import collections
import gzip
import logging
import pickle
import sys

# Third Party
import environ
import redis
from listcrunch import crunch_collection
from PIL import Image
from redis.exceptions import RedisError

env = environ.Env()
logger = logging.getLogger(__name__)

# Imports based on execution context
if env.str("ENVIRONMENT").startswith("local"):
    from documentcloud.common import path, redis_fields
    from documentcloud.common.environment import (
        get_http_data,
        get_pubsub_data,
        encode_pubsub_data,
        publisher,
        storage,
    )
    from documentcloud.common.serverless import utils
    from documentcloud.common.serverless.error_handling import pubsub_function
    from documentcloud.documents.processing.info_and_image.pdfium import (
        StorageHandler,
        Workspace,
    )
else:
    from common import path, redis_fields
    from common.environment import (
        get_http_data,
        get_pubsub_data,
        encode_pubsub_data,
        publisher,
        storage,
    )
    from common.serverless import utils
    from common.serverless.error_handling import pubsub_function
    from pdfium import StorageHandler, Workspace

    # only initialize sentry on serverless
    import sentry_sdk
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

    sentry_sdk.init(dsn=env("SENTRY_DSN"), integrations=[AwsLambdaIntegration()])


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
REDIS = utils.get_redis()

# Topic names for the messaging queue
PDF_PROCESS_TOPIC = publisher.topic_path(
    "documentcloud", env.str("PDF_PROCESS_TOPIC", default="pdf-process")
)
IMAGE_EXTRACT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("IMAGE_EXTRACT_TOPIC", default="image-extraction")
)
OCR_TOPIC = publisher.topic_path(
    "documentcloud", env.str("OCR_TOPIC", default="ocr-extraction")
)


def initialize_redis_page_data(doc_id, page_count):
    """Initial Redis fields to manage page dimensions and processing"""
    dimensions_field = redis_fields.dimensions(doc_id)
    image_bits_field = redis_fields.image_bits(doc_id)
    text_bits_field = redis_fields.text_bits(doc_id)

    def dimensions_field_update(pipeline):
        existing_dimensions = pipeline.smembers(dimensions_field)

        # Put the pipeline back in multi mode
        pipeline.multi()

        # Set the page count field
        pipeline.set(redis_fields.page_count(doc_id), page_count)

        # Set pages and texts remaining to page count
        pipeline.set(redis_fields.images_remaining(doc_id), page_count)
        pipeline.set(redis_fields.texts_remaining(doc_id), page_count)

        # Set Redis bit arrays flooded to 0 to track each page
        pipeline.delete(image_bits_field)
        pipeline.delete(text_bits_field)
        pipeline.setbit(image_bits_field, page_count - 1, 0)
        pipeline.setbit(text_bits_field, page_count - 1, 0)

        # Remove any existing dimensions that may be lingering
        if existing_dimensions is not None:
            for dimension in existing_dimensions:
                pipeline.delete(redis_fields.page_dimension(doc_id, dimension))
        pipeline.delete(dimensions_field)

    # Ensure atomicity while getting a value with the transaction wrapper around WATCH
    # See https://pypi.org/project/redis/#pipelines for details
    REDIS.transaction(dimensions_field_update, dimensions_field)


def extract_pagecount(doc_id, slug):
    """Parse a PDF and write files to cache PDF information and dimensions.

    Returns:
        A tuple containing the number of pages in the PDF file and an array of
        page sizes.
    """
    # Get the page sizes and initialize a cache of page positions
    doc_path = path.doc_path(doc_id, slug)
    with Workspace() as workspace, StorageHandler(
        storage, doc_path, record=True
    ) as pdf_file, workspace.load_document_custom(pdf_file) as doc:
        page_count = doc.page_count
        cached = pdf_file.cache

    # Create an index file that stores the memory locations of each page of the
    # PDF file.
    index_path = path.index_path(doc_id, slug)
    with storage.open(index_path, "wb") as pickle_file, gzip.open(
        pickle_file, "wb"
    ) as zip_file:
        pickle.dump(cached, zip_file)

    # Pass the page_count back to the caller.
    return page_count


def get_redis_pagespec(doc_id):
    """Get the dimensions of all pages in a convenient format using Redis"""
    dimensions_field = redis_fields.dimensions(doc_id)

    pipeline = REDIS.pipeline()

    # We cannot use the convenience transacation wrapper since values we watch
    # are dynamic
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
                page_dimension_field = redis_fields.page_dimension(
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
        except redis.exceptions.WatchError:
            continue
        finally:
            pipeline.reset()

    return pagespec


def write_pagespec(doc_id, slug):
    """Extract and write the dimensions of all pages to a pagespec file"""
    pagespec = get_redis_pagespec(doc_id)
    crunched_pagespec = crunch_collection(pagespec)
    with storage.open(path.pagesize_path(doc_id, slug), "w") as pagesize_file:
        pagesize_file.write(crunched_pagespec)

    # Send pagespec update
    utils.send_update(REDIS, doc_id, {"page_spec": crunched_pagespec})


def process_pdf(request, _context=None):
    """Process a PDF file's information and launch extraction tasks."""
    data = get_http_data(request)
    doc_id = data["doc_id"]

    # Initialize the processing environment
    utils.initialize(REDIS, doc_id)

    # Launch PDF processing via pubsub
    publisher.publish(PDF_PROCESS_TOPIC, data=encode_pubsub_data(data))

    return "Ok"


@pubsub_function(REDIS, PDF_PROCESS_TOPIC)
def process_pdf_internal(data, _context=None):
    """Process a PDF file's information and launch extraction tasks."""
    data = get_pubsub_data(data)

    doc_id = data["doc_id"]
    slug = data["slug"]

    # Extract the page count and store it in Redis
    page_count = extract_pagecount(doc_id, slug)
    initialize_redis_page_data(doc_id, page_count)

    # Update the model with the page count
    utils.send_update(REDIS, doc_id, {"page_count": page_count})

    # Kick off image processing tasks
    for i in range(0, page_count, IMAGE_BATCH):
        # Trigger image extraction for each page
        pages = list(range(i, min(i + IMAGE_BATCH, page_count)))
        publisher.publish(
            IMAGE_EXTRACT_TOPIC,
            data=encode_pubsub_data({"doc_id": doc_id, "slug": slug, "pages": pages}),
        )

    return "Ok"


def extract_single_page(doc_id, slug, doc, page_number):
    """Internal method to extract a single page from a PDF file as an image.

    Returns:
        The path to the newly rendered large image path.
    """
    # Load the page from the PDF
    page = doc.load_page(page_number)
    large_image_path = path.page_image_path(
        doc_id, slug, page_number, IMAGE_WIDTHS[0][0]
    )

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
            path.page_image_path(doc_id, slug, page_number, image_suffix), "wb"
        ) as img_f:
            img.save(img_f, format=IMAGE_SUFFIX[1:].lower())

        # TODO: trigger update when thumbnail image is parsed

    return (large_image_path, page.width, page.height)


@pubsub_function(REDIS, IMAGE_EXTRACT_TOPIC)
def extract_image(data, _context=None):
    """Renders (extracts) an image from a PDF file."""
    data = get_pubsub_data(data)

    doc_id = data["doc_id"]
    slug = data["slug"]
    doc_path = path.doc_path(doc_id, slug)
    page_numbers = data["pages"]  # The page numbers to extract
    index_path = path.index_path(doc_id, slug)  # The path to the PDF index file

    # Store a queue of pages to OCR to fill the batch
    ocr_queue = []

    def flush(ocr_queue):
        if not ocr_queue:
            return

        # Trigger ocr pipeline
        publisher.publish(
            OCR_TOPIC,
            data=encode_pubsub_data({"paths_and_numbers": ocr_queue, "doc_id": doc_id}),
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

    images_remaining_field = redis_fields.images_remaining(doc_id)
    image_bits_field = redis_fields.image_bits(doc_id)
    with Workspace() as workspace, StorageHandler(
        storage, doc_path, record=False, playback=True, cache=cached
    ) as pdf_file, workspace.load_document_custom(pdf_file) as doc:
        for page_number in page_numbers:
            # Only process if it has not processed previously
            if REDIS.getbit(image_bits_field, page_number) == 0:
                # Extract the image.
                large_image_path, width, height = extract_single_page(
                    doc_id, slug, doc, page_number
                )
                page_dimension = f"{width}x{height}"

                # Update Redis properties atomically
                pipeline = REDIS.pipeline()

                # Update the page dimensions in Redis
                pipeline.sadd(redis_fields.dimensions(doc_id), page_dimension)
                pipeline.sadd(
                    redis_fields.page_dimension(doc_id, page_dimension), page_number
                )
                # Decrement pages remaining and set the bit for the page off in Redis
                pipeline.decr(images_remaining_field)
                pipeline.setbit(image_bits_field, page_number, 1)
                images_remaining = pipeline.execute()[2]

                if images_remaining == 0:
                    write_pagespec(doc_id, slug)

            # Prepare the image to be OCRd.
            ocr_queue.append([doc_id, slug, page_number, large_image_path])
            check_and_flush(ocr_queue)

    flush(ocr_queue)

    return "Ok"


def get_progress(request, _context=None):
    """Get progress information from redis"""
    data = get_http_data(request)
    doc_id = data["doc_id"]

    try:
        with REDIS.pipeline() as pipeline:
            pipeline.get(redis_fields.images_remaining(doc_id))
            pipeline.get(redis_fields.texts_remaining(doc_id))
            images, texts = [int(i) if i is not None else i for i in pipeline.execute()]
    except RedisError as exc:
        logger.error("RedisError during get_progress: %s", exc, exc_info=sys.exc_info())
        images, texts = (None, None)

    return {"images": images, "texts": texts}
