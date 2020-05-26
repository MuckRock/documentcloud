# Standard Library
import collections
import csv
import gzip
import io
import json
import pickle

# Third Party
import environ
import redis
from listcrunch import crunch_collection
from PIL import Image

env = environ.Env()

# Imports based on execution context
if env.str("ENVIRONMENT").startswith("local"):
    from documentcloud.common import path, redis_fields, access_choices
    from documentcloud.common.environment import (
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
    from common import path, redis_fields, access_choices
    from common.environment import (
        get_pubsub_data,
        encode_pubsub_data,
        publisher,
        storage,
    )
    from common.serverless import utils
    from common.serverless.error_handling import pubsub_function
    from pdfium import StorageHandler, Workspace

    # only initialize sentry on serverless
    # pylint: disable=import-error
    import sentry_sdk
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    # pylint: enable=import-error

    sentry_sdk.init(
        dsn=env("SENTRY_DSN"), integrations=[AwsLambdaIntegration(), RedisIntegration()]
    )


IMAGE_SUFFIX = ".gif"
IMAGE_BATCH = env.int(
    "EXTRACT_IMAGE_BATCH", default=55
)  # Number of images to extract with each function
OCR_BATCH = env.int("OCR_BATCH", 1)  # Number of pages to OCR with each function
PDF_SIZE_LIMIT = env.int("PDF_SIZE_LIMIT", 501 * 1024 * 1024)
BLOCK_SIZE = env.int(
    "BLOCK_SIZE", 8 * 1024 * 1024
)  # Block size to use for reading chunks of the PDF
TEXT_READ_BATCH = env.int("TEXT_READ_BATCH", 5)
IMPORT_OCR_VERSION = env.str("IMPORT_OCR_VERSION", default="dc-import")


def parse_extract_width(width_str):
    extract_width = width_str.split(":")
    return [extract_width[0], int(extract_width[1])]


IMAGE_WIDTHS = [
    parse_extract_width(x)
    for x in env.list(
        "IMAGE_EXTRACT_WIDTHS",
        default=[
            "xlarge:2000",
            "large:1000",
            "normal:700",
            "small:180",
            "thumbnail:60",
        ],
    )
]  # width of images to OCR
# Index of image widths to use for OCR
OCR_IMAGE_INDEX = env.int("IMAGE_EXTRACT_OCR_INDEX", 1)
REDIS = utils.get_redis()

# Topic names for the messaging queue
PDF_PROCESS_TOPIC = publisher.topic_path(
    "documentcloud", env.str("PDF_PROCESS_TOPIC", default="pdf-process")
)
PAGE_CACHE_TOPIC = publisher.topic_path(
    "documentcloud", env.str("PAGE_CACHE_TOPIC", default="page-cache")
)
IMAGE_EXTRACT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("IMAGE_EXTRACT_TOPIC", default="image-extraction")
)
ASSEMBLE_TEXT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("ASSEMBLE_TEXT_TOPIC", default="assemble-text")
)
REDACT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("REDACT_TOPIC", default="redact-doc")
)
OCR_TOPIC = publisher.topic_path(
    "documentcloud", env.str("OCR_TOPIC", default="ocr-extraction")
)

START_IMPORT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("START_IMPORT_TOPIC", default="start-import")
)
IMPORT_DOCUMENT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("IMPORT_DOCUMENT_TOPIC", default="import-document")
)
READ_PAGE_TEXT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("READ_PAGE_TEXT_TOPIC", default="read-page-text")
)
FINISH_IMPORT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("FINISH_IMPORT_TOPIC", default="finish-import")
)


class PdfSizeError(Exception):
    pass


def initialize_redis_page_data(doc_id, page_count):
    """Initialize Redis fields to manage page dimensions and processing"""
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

        # Remove any existing page text
        pipeline.delete(redis_fields.page_text(doc_id))

    # Ensure atomicity while getting a value with the transaction wrapper around WATCH
    # See https://pypi.org/project/redis/#pipelines for details
    REDIS.transaction(dimensions_field_update, dimensions_field)


def initialize_partial_redis_page_data(doc_id, page_count, dirty_pages):
    """Initialize Redis fields to manage processing for partial updates.

    dirty_pages specifies which pages need to be reextracted. For instance,
    after redacting several pages, only those pages need to be reprocessed
    after the whole document is remade.
    """

    image_bits_field = redis_fields.image_bits(doc_id)
    text_bits_field = redis_fields.text_bits(doc_id)

    pipeline = REDIS.pipeline()
    pipeline.set(redis_fields.page_count(doc_id), page_count)

    # Set images/texts remaining equal to number of dirty pages
    pipeline.set(redis_fields.images_remaining(doc_id), len(dirty_pages))
    pipeline.set(redis_fields.texts_remaining(doc_id), len(dirty_pages))

    # Set Redis bit arrays flooded to 1 to track each page.
    # Just the dirty pages will be set to 0 to indicate
    # reprocessing is needed.
    pipeline.delete(image_bits_field)
    pipeline.delete(text_bits_field)
    for i in range(page_count):
        pipeline.setbit(image_bits_field, i, 0 if i in dirty_pages else 1)
        pipeline.setbit(text_bits_field, i, 0 if i in dirty_pages else 1)

    # Remove any existing page text
    pipeline.delete(redis_fields.page_text(doc_id))

    # Execute the pipeline atomically
    pipeline.execute()


def write_cache(filename, cache, access):
    """Helper method to write a cache file."""
    mem_file = io.BytesIO()
    with gzip.open(mem_file, "wb") as zip_file:
        pickle.dump(cache, zip_file)

    storage.simple_upload(filename, mem_file.getvalue(), access=access)
    mem_file.close()


def read_cache(filename):
    """Helper method to read a cache file."""
    with storage.open(filename, "rb") as pickle_file, gzip.open(
        pickle_file, "rb"
    ) as zip_file:
        return pickle.load(zip_file)


def write_text_file(text_path, text, access):
    """Helper method to write text file."""
    storage.simple_upload(text_path, text.encode("utf8"), access=access)


def update_pagespec(doc_id):
    """Extract and send the dimensions of all pages in pagespec format"""
    pagespec = get_redis_pagespec(doc_id)
    crunched_pagespec = crunch_collection(pagespec)

    # Send pagespec update
    utils.send_update(REDIS, doc_id, {"page_spec": crunched_pagespec})


def extract_pagecount(doc_id, slug):
    """Parse a PDF and write files to cache PDF information and dimensions.

    Returns:
        A tuple containing the number of pages in the PDF file and an array of
        page sizes.
    """
    # Get the page sizes and initialize a cache of page positions
    doc_path = path.doc_path(doc_id, slug)
    with Workspace() as workspace, StorageHandler(
        storage, doc_path, record=False, block_size=BLOCK_SIZE
    ) as pdf_file, workspace.load_document_custom(pdf_file) as doc:
        page_count = doc.page_count

    # Pass the page_count back to the caller.
    return page_count


def redact_document_and_overwrite(doc_id, slug, access, redactions):
    """Redacts a document and overwrites the original PDF."""
    doc_path = path.doc_path(doc_id, slug)

    with Workspace() as workspace, workspace.load_document_entirely(
        storage, doc_path
    ) as doc:
        new_doc = doc.redact_pages(redactions)
        # Overwrite the original doc
        new_doc.save(storage, doc_path, access)


def get_redis_pagespec(doc_id):
    """Get the dimensions of all pages in a convenient format using Redis"""
    # pylint: disable=too-many-nested-blocks
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


@pubsub_function(REDIS, PAGE_CACHE_TOPIC)
def process_page_cache(data, _context=None):
    """Memoize the memory accesses of all the pages of a PDF in a cache."""
    data = get_pubsub_data(data)

    doc_id = data["doc_id"]
    slug = data["slug"]
    access = data.get("access", access_choices.PRIVATE)
    dirty = data.get("dirty")
    force_ocr = data.get("force_ocr", False)

    doc_path = path.doc_path(doc_id, slug)

    # Read the entire document into memory
    with Workspace() as workspace, StorageHandler(
        storage, doc_path, record=True, playback=False, cache=None, read_all=True
    ) as pdf_file, workspace.load_document_custom(pdf_file) as doc:
        # Load the final page to memoize all page accesses
        page_count = doc.page_count
        doc.load_page(page_count - 1)
        cached = pdf_file.cache

        # Create an index file that stores the memory locations of each page of the
        # PDF file.
        write_cache(path.index_path(doc_id, slug), cached, access)

        # Method to publish image batches
        def pub(pages):
            if pages:
                publisher.publish(
                    IMAGE_EXTRACT_TOPIC,
                    data=encode_pubsub_data(
                        {
                            "doc_id": doc_id,
                            "slug": slug,
                            "access": access,
                            "pages": pages,
                            "partial": dirty,
                            "force_ocr": force_ocr,
                        }
                    ),
                )

        # Trigger image extraction tasks for each page
        if dirty:
            # If only dirty pages are flagged, process the relevant ones in batches
            dirty = sorted(dirty)
            for i in range(0, len(dirty), IMAGE_BATCH):
                pages = [dirty[i] for i in range(0, min(IMAGE_BATCH, len(dirty)))]
                pub(pages)
        else:
            # Otherwise, process all pages in batches
            for i in range(0, page_count, IMAGE_BATCH):
                pages = list(range(i, min(i + IMAGE_BATCH, page_count)))
                pub(pages)


@pubsub_function(REDIS, PDF_PROCESS_TOPIC)
def process_pdf(data, _context=None):
    """Process a PDF file's information and launch extraction tasks."""
    data = get_pubsub_data(data)

    doc_id = data["doc_id"]
    slug = data["slug"]
    access = data.get("access", access_choices.PRIVATE)
    force_ocr = data.get("force_ocr", False)

    # Ensure PDF size is within the limit
    doc_path = path.doc_path(doc_id, slug)
    if storage.size(doc_path) > PDF_SIZE_LIMIT:
        # If not, remove the PDF
        storage.delete(path.path(doc_id))
        raise PdfSizeError()

    # Extract the page count and store it in Redis
    page_count = extract_pagecount(doc_id, slug)
    initialize_redis_page_data(doc_id, page_count)

    # Update the model with the page count
    utils.send_update(REDIS, doc_id, {"page_count": page_count})

    # Kick off page cache processing
    publisher.publish(
        PAGE_CACHE_TOPIC,
        data=encode_pubsub_data(
            {"doc_id": doc_id, "slug": slug, "access": access, "force_ocr": force_ocr}
        ),
    )

    return "Ok"


def get_large_image_path(doc_id, slug, page_number):
    """Return the path for the largest image size."""
    return path.page_image_path(doc_id, slug, page_number, IMAGE_WIDTHS[0][0])


def extract_single_page(doc_id, slug, access, page, page_number, large_image_path):
    """Internal method to extract a single page from a PDF file as an image.

    Returns:
        The page dimensions.
    """

    # Extract the page as an image with a certain width
    bmp = page.get_bitmap(IMAGE_WIDTHS[0][1], None)
    img_buffer = bmp.render(storage, large_image_path, access)

    # Resize to render smaller page sizes
    for [image_suffix, image_width] in IMAGE_WIDTHS[1:]:
        img = img_buffer.resize(
            (image_width, round(img_buffer.height * (image_width / img_buffer.width))),
            Image.ANTIALIAS,
        )

        mem_file = io.BytesIO()
        img.save(mem_file, format=IMAGE_SUFFIX[1:].lower())
        storage.simple_upload(
            path.page_image_path(doc_id, slug, page_number, image_suffix),
            mem_file.getvalue(),
            access=access,
        )
        mem_file.close()

    return (page.width, page.height)


@pubsub_function(REDIS, IMAGE_EXTRACT_TOPIC)
def extract_image(data, _context=None):
    """Renders (extracts) an image from a PDF file."""
    # pylint: disable=too-many-locals
    data = get_pubsub_data(data)

    doc_id = data["doc_id"]
    slug = data["slug"]
    access = data.get("access", access_choices.PRIVATE)
    doc_path = path.doc_path(doc_id, slug)
    page_numbers = data["pages"]  # The page numbers to extract
    partial = data["partial"]  # Whether it is a partial update (e.g. redaction) or not
    force_ocr = data["force_ocr"]

    # Store a queue of pages to OCR to fill the batch
    ocr_queue = []

    def flush(ocr_queue):
        if not ocr_queue:
            return

        # Trigger ocr pipeline
        publisher.publish(
            OCR_TOPIC,
            data=encode_pubsub_data(
                {
                    "paths_and_numbers": ocr_queue,
                    "doc_id": doc_id,
                    "slug": slug,
                    "access": access,
                    "partial": partial,
                    "force_ocr": force_ocr,
                }
            ),
        )

        ocr_queue.clear()

    def check_and_flush(ocr_queue):
        if len(ocr_queue) >= OCR_BATCH:
            flush(ocr_queue)

    # Open the PDF file with the cached index
    cached = read_cache(path.index_path(doc_id, slug))

    with Workspace() as workspace, StorageHandler(
        storage,
        doc_path,
        record=False,
        playback=True,
        cache=cached,
        read_all=False,
        block_size=BLOCK_SIZE,
    ) as pdf_file, workspace.load_document_custom(pdf_file) as doc:
        for page_number in page_numbers:
            # Only process if it has not processed previously
            large_image_path = path.page_image_path(
                doc_id, slug, page_number, IMAGE_WIDTHS[0][0]
            )
            page = None
            if not utils.page_extracted(REDIS, doc_id, page_number):
                # Extract the image.
                if page is None:
                    page = doc.load_page(page_number)
                width, height = extract_single_page(
                    doc_id, slug, access, page, page_number, large_image_path
                )
                page_dimension = f"{width}x{height}"

                if not partial:
                    # Update the page dimensions in Redis atomically
                    pipeline = REDIS.pipeline()
                    pipeline.sadd(redis_fields.dimensions(doc_id), page_dimension)
                    pipeline.sadd(
                        redis_fields.page_dimension(doc_id, page_dimension), page_number
                    )
                    pipeline.execute()

                images_finished = utils.register_page_extracted(
                    REDIS, doc_id, page_number
                )

                # Write the pagespec dimensions if all images have finished and
                # it's not a partial update.
                if images_finished and not partial:
                    update_pagespec(doc_id)

            if not utils.page_ocrd(REDIS, doc_id, page_number):
                # Extract page text if possible
                if force_ocr:
                    text = None
                else:
                    if page is None:
                        page = doc.load_page(page_number)

                    text = page.text

                if text is not None and len(text.strip()) > 0:
                    text_path = path.page_text_path(doc_id, slug, page_number)

                    # Page already has text inside
                    write_text_file(text_path, text, access)
                    utils.write_page_text(REDIS, doc_id, page_number, text, None)

                    # Decrement the texts remaining, sending complete if done.
                    texts_finished = utils.register_page_ocrd(
                        REDIS, doc_id, page_number
                    )
                    if texts_finished:
                        publisher.publish(
                            ASSEMBLE_TEXT_TOPIC,
                            encode_pubsub_data(
                                {
                                    "doc_id": doc_id,
                                    "slug": slug,
                                    "access": access,
                                    "partial": partial,
                                }
                            ),
                        )
                        return "Ok"
                else:
                    # Prepare the image to be OCRd.
                    ocr_image_path = path.page_image_path(
                        doc_id, slug, page_number, IMAGE_WIDTHS[OCR_IMAGE_INDEX][0]
                    )
                    ocr_queue.append([page_number, ocr_image_path])
                    check_and_flush(ocr_queue)

    flush(ocr_queue)

    return "Ok"


@pubsub_function(REDIS, ASSEMBLE_TEXT_TOPIC)
def assemble_page_text(data, _context=None):
    """Assembles a single page text file containing the doc's entire page text."""
    data = get_pubsub_data(data)

    doc_id = data["doc_id"]
    slug = data["slug"]
    access = data.get("access", access_choices.PRIVATE)
    partial = data["partial"]  # Whether it is a partial update (e.g. redaction) or not
    is_import = data.get("import", False)
    if is_import:
        org_id = data["org_id"]

    results = utils.get_all_page_text(REDIS, doc_id, is_import)

    if partial:
        # Patch the old results in if it's a partial update
        with storage.open(path.json_text_path(doc_id, slug), "rb") as json_file:
            old_results = json.loads(json_file.read())

        for result in results["pages"]:
            page = result["page"]
            # Patch in the new page
            old_results["pages"][page] = result

        # Patch in the updated time
        old_results["updated"] = results["updated"]

        # Overwrite the original results
        results = old_results

    if not is_import:
        # Compile concatenated text only outside of import mode
        # (we don't want to overwrite the previous file)
        concatenated_text = b"\n\n".join(
            [page["contents"].encode("utf-8") for page in results["pages"]]
        )

        # Write the concatenated text file
        storage.simple_upload(
            path.text_path(doc_id, slug), concatenated_text, access=access
        )

    # Write the json text file
    storage.simple_upload(
        path.json_text_path(doc_id, slug),
        json.dumps(results).encode("utf-8"),
        access=access,
    )

    if is_import:
        # Clean up Redis page text
        REDIS.delete(
            redis_fields.texts_remaining(doc_id),
            redis_fields.text_bits(doc_id),
            redis_fields.page_text(doc_id),
        )

        publisher.publish(
            FINISH_IMPORT_TOPIC,
            encode_pubsub_data({"org_id": org_id, "doc_id": doc_id, "slug": slug}),
        )
    else:
        utils.send_complete(REDIS, doc_id)

    return "Ok"


@pubsub_function(REDIS, REDACT_TOPIC)
def redact_doc(data, _context=None):
    """Redacts a document and reprocesses altered pages."""
    data = get_pubsub_data(data)

    doc_id = data["doc_id"]
    slug = data["slug"]
    access = data.get("access", access_choices.PRIVATE)
    redactions = data["redactions"]

    # Get dirty pages
    dirty_pages = set()
    for redaction in redactions:
        dirty_pages.add(redaction["page_number"])

    # Perform the actual redactions
    redact_document_and_overwrite(doc_id, slug, access, redactions)

    page_count = extract_pagecount(doc_id, slug)
    initialize_partial_redis_page_data(doc_id, page_count, dirty_pages)

    # Kick off page cache processing
    dirty_pages_list = sorted(dirty_pages)
    publisher.publish(
        PAGE_CACHE_TOPIC,
        data=encode_pubsub_data(
            {
                "doc_id": doc_id,
                "slug": slug,
                "access": access,
                "dirty": dirty_pages_list,
            }
        ),
    )

    return "Ok"


@pubsub_function(REDIS, START_IMPORT_TOPIC)
def start_import(data, _context=None):
    """Reads in an org's import CSV and starts the import process."""
    data = get_pubsub_data(data)
    org_id = data["org_id"]

    with storage.open(path.import_org_csv(org_id), "r") as csvfile:
        csvreader = csv.reader(csvfile)
        next(csvreader)  # discard headers

        doc_ids = []
        for row in csvreader:
            # Pull the doc id (1st column) and slug (7th column)
            doc_ids.append((row[0], row[6]))

    # Initialize Redis
    REDIS.set(redis_fields.import_docs_remaining(org_id), len(doc_ids))

    for doc_id, slug in doc_ids:
        publisher.publish(
            IMPORT_DOCUMENT_TOPIC,
            encode_pubsub_data({"org_id": org_id, "doc_id": doc_id, "slug": slug}),
        )

    return "Ok"


@pubsub_function(REDIS, IMPORT_DOCUMENT_TOPIC, skip_processing_check=True)
def import_document(data, _context=None):
    """Handles the import process for a single document."""
    # pylint: disable=too-many-locals
    data = get_pubsub_data(data)
    org_id = data["org_id"]
    doc_id = data["doc_id"]
    slug = data["slug"]

    # Get the pagespec from the PDF
    pagespec = collections.defaultdict(list)
    doc_path = path.doc_path(doc_id, slug)
    try:
        with Workspace() as workspace, StorageHandler(
            storage, doc_path, record=False, playback=False, cache=None, read_all=True
        ) as pdf_file, workspace.load_document_custom(pdf_file) as doc:
            # Get the page spec by grabbing the dimension from each page
            page_count = doc.page_count
            for page_number in range(page_count):
                page = doc.load_page(page_number)
                pagespec[f"{page.width}x{page.height}"].append(page_number)
    except ValueError:
        # document was not found
        REDIS.hset(redis_fields.import_pagespecs(org_id), doc_id, "")
        publisher.publish(
            FINISH_IMPORT_TOPIC,
            encode_pubsub_data({"org_id": org_id, "doc_id": doc_id, "slug": slug}),
        )
        return

    # Set the pagespec
    crunched_pagespec = crunch_collection(pagespec)

    # Run a Redis pipeline
    pipeline = REDIS.pipeline()
    pipeline.hset(redis_fields.import_pagespecs(org_id), f"{doc_id}", crunched_pagespec)

    # Set Redis texts remaining to page count
    pipeline.set(redis_fields.texts_remaining(doc_id), page_count)

    # Set Redis text bits field flooded to 0 to track each page
    text_bits_field = redis_fields.text_bits(doc_id)
    pipeline.delete(text_bits_field)
    pipeline.setbit(text_bits_field, page_count - 1, 0)
    pipeline.execute()

    # Kick off reading text files
    for i in range(0, page_count, TEXT_READ_BATCH):
        pages = list(range(i, min(i + TEXT_READ_BATCH, page_count)))
        publisher.publish(
            READ_PAGE_TEXT_TOPIC,
            encode_pubsub_data(
                {"org_id": org_id, "doc_id": doc_id, "slug": slug, "pages": pages}
            ),
        )


@pubsub_function(REDIS, READ_PAGE_TEXT_TOPIC, skip_processing_check=True)
def read_page_text(data, _context=None):
    """A function to read page text from documents in batch."""
    data = get_pubsub_data(data)
    org_id = data["org_id"]
    doc_id = data["doc_id"]
    slug = data["slug"]
    pages = data["pages"]

    for page_number in pages:
        text_path = path.page_text_path(doc_id, slug, page_number)
        with storage.open(text_path, "r") as text_file:
            text = text_file.read()
            utils.write_page_text(REDIS, doc_id, page_number, text, IMPORT_OCR_VERSION)

        # Decrement the texts remaining, assembling text if done.
        texts_finished = utils.register_page_ocrd(REDIS, doc_id, page_number)
        if texts_finished:
            publisher.publish(
                ASSEMBLE_TEXT_TOPIC,
                encode_pubsub_data(
                    {
                        "doc_id": doc_id,
                        "slug": slug,
                        "access": access_choices.PRIVATE,
                        "import": True,
                        "org_id": org_id,
                        "partial": False,
                    }
                ),
            )


@pubsub_function(REDIS, FINISH_IMPORT_TOPIC, skip_processing_check=True)
def finish_import(data, _context=None):
    """Finishes off the import process"""
    data = get_pubsub_data(data)
    org_id = data["org_id"]
    doc_id = data["doc_id"]

    import_docs_remaining = REDIS.decr(redis_fields.import_docs_remaining(org_id))

    if import_docs_remaining == 0:
        # Done importing! Assemble the resulting CSV

        # Extract pagespec information from Redis
        pagespecs = {}
        redis_pagespecs = REDIS.hgetall(redis_fields.import_pagespecs(org_id))
        for doc_id, pagespec in redis_pagespecs.items():
            pagespecs[doc_id.decode()] = pagespec.decode()

        # Assemble new CSV as additional column on old import CSV
        rows = []
        with storage.open(path.import_org_csv(org_id), "r") as csvfile:
            csvreader = csv.reader(csvfile)
            headers = next(csvreader)
            rows.append(headers + ["pagespec"])

            for row in csvreader:
                doc_id = row[0]
                pagespec = pagespecs[doc_id]
                # Add pagespec to each row
                rows.append(row + [pagespec])

        # Write the new pagespec-enhanced CSV
        with storage.open(path.import_org_pagespec_csv(org_id), "w") as new_csv_file:
            csvwriter = csv.writer(new_csv_file)
            for row in rows:
                csvwriter.writerow(row)

        # Clean up Redis
        REDIS.delete(
            redis_fields.import_docs_remaining(org_id),
            redis_fields.import_pagespecs(org_id),
        )
