# Standard Library
import collections
import copy
import csv
import gzip
import io
import itertools
import json
import logging
import pickle
import time
from random import randint

# Third Party
import environ
import pdfplumber
import redis
from botocore.exceptions import ClientError
from listcrunch import crunch_collection
from PIL import Image

env = environ.Env()
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logging.getLogger("pdfminer").setLevel(logging.WARNING)

# remove this when done with import code
# pylint: disable=too-many-lines

# pylint: disable=import-error

# Imports based on execution context
if env.str("ENVIRONMENT").startswith("local"):
    # DocumentCloud
    from documentcloud.documents.processing.info_and_image import graft
    from documentcloud.common import access_choices, path, redis_fields
    from documentcloud.common.environment import (
        encode_pubsub_data,
        get_pubsub_data,
        publisher,
        storage,
    )
    from documentcloud.common.serverless import utils
    from documentcloud.common.serverless.error_handling import (
        pubsub_function,
        pubsub_function_import,
    )
    from documentcloud.documents.processing.info_and_image.graft_adapter import (
        GraftContext,
    )
    from documentcloud.documents.processing.info_and_image.pdfium import (
        StorageHandler,
        Workspace,
    )
else:
    # Third Party
    import graft

    # only initialize sentry on serverless
    import sentry_sdk
    from common import access_choices, path, redis_fields
    from common.environment import (
        encode_pubsub_data,
        get_pubsub_data,
        publisher,
        storage,
    )
    from common.serverless import utils
    from common.serverless.error_handling import pubsub_function, pubsub_function_import
    from graft_adapter import GraftContext
    from pdfium import StorageHandler, Workspace
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=env("SENTRY_DSN"), integrations=[AwsLambdaIntegration(), RedisIntegration()]
    )


IMAGE_SUFFIX = ".gif"
IMAGE_BATCH = env.int(
    "EXTRACT_IMAGE_BATCH", default=55
)  # Number of images to extract with each function
OCR_BATCH = env.int("OCR_BATCH", 1)  # Number of pages to OCR with each function
TEXT_POSITION_BATCH = env.int(
    "TEXT_POSITION_BATCH", 3
)  # Number of pages to pull text positions from with each function
PDF_SIZE_LIMIT = env.int("PDF_SIZE_LIMIT", 501 * 1024 * 1024)
BLOCK_SIZE = env.int(
    "BLOCK_SIZE", 8 * 1024 * 1024
)  # Block size to use for reading chunks of the PDF
TEXT_READ_BATCH = env.int("TEXT_READ_BATCH", 1000)
IMPORT_OCR_VERSION = env.str("IMPORT_OCR_VERSION", default="dc-import")
IMPORT_DOCS_BATCH = env.int("IMPORT_DOCS_BATCH", 10000)


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
OCR_TOPIC = publisher.topic_path(
    "documentcloud", env.str("OCR_TOPIC", default="ocr-extraction-dev")
)
ASSEMBLE_TEXT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("ASSEMBLE_TEXT_TOPIC", default="assemble-text")
)
TEXT_POSITION_EXTRACT_TOPIC = publisher.topic_path(
    "documentcloud",
    env.str("TEXT_POSITION_EXTRACT_TOPIC", default="text-position-extraction"),
)
REDACT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("REDACT_TOPIC", default="redact-doc")
)
MODIFY_TOPIC = publisher.topic_path(
    "documentcloud", env.str("MODIFY_TOPIC", default="modify-doc")
)
START_IMPORT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("START_IMPORT_TOPIC", default="start-import")
)
IMPORT_DOCUMENT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("IMPORT_DOCUMENT_TOPIC", default="import-document")
)
FINISH_IMPORT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("FINISH_IMPORT_TOPIC", default="finish-import")
)

ANGLE_TABLE = {"": 0, "cc": 1, "hw": 2, "ccw": 3}


def millis():
    """Get the current time in milliseconds"""
    return int(round(time.time() * 1000))


class PdfSizeError(Exception):
    pass


def initialize_redis_page_data(doc_id, page_count):
    """Initialize Redis fields to manage page dimensions and processing"""
    dimensions_field = redis_fields.dimensions(doc_id)
    image_bits_field = redis_fields.image_bits(doc_id)
    text_bits_field = redis_fields.text_bits(doc_id)
    text_position_bits_field = redis_fields.text_position_bits(doc_id)

    def dimensions_field_update(pipeline):
        existing_dimensions = pipeline.smembers(dimensions_field)

        # Put the pipeline back in multi mode
        pipeline.multi()

        # Set the page count field
        pipeline.set(redis_fields.page_count(doc_id), page_count)

        # Set pages and texts remaining to page count
        pipeline.set(redis_fields.images_remaining(doc_id), page_count)
        pipeline.set(redis_fields.texts_remaining(doc_id), page_count)
        pipeline.set(redis_fields.text_positions_remaining(doc_id), page_count)

        # Set Redis bit arrays flooded to 0 to track each page
        pipeline.delete(image_bits_field)
        pipeline.delete(text_bits_field)
        pipeline.delete(text_position_bits_field)
        pipeline.setbit(image_bits_field, page_count - 1, 0)
        pipeline.setbit(text_bits_field, page_count - 1, 0)
        pipeline.setbit(text_position_bits_field, page_count - 1, 0)

        # Remove any existing dimensions that may be lingering
        if existing_dimensions is not None:
            for dimension in existing_dimensions:
                dimension = dimension.decode("utf8")
                pipeline.delete(redis_fields.page_dimension(doc_id, dimension))
        pipeline.delete(dimensions_field)

        # Remove any existing page text
        pipeline.delete(redis_fields.page_text(doc_id))
        pipeline.delete(redis_fields.page_text_pdf(doc_id))

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
    text_position_bits_field = redis_fields.text_position_bits(doc_id)

    pipeline = REDIS.pipeline()
    pipeline.set(redis_fields.page_count(doc_id), page_count)

    # Set images/texts remaining equal to number of dirty pages
    pipeline.set(redis_fields.images_remaining(doc_id), len(dirty_pages))
    pipeline.set(redis_fields.texts_remaining(doc_id), len(dirty_pages))
    pipeline.set(redis_fields.text_positions_remaining(doc_id), len(dirty_pages))

    # Set Redis bit arrays flooded to 1 to track each page.
    # Just the dirty pages will be set to 0 to indicate
    # reprocessing is needed.
    pipeline.delete(image_bits_field)
    pipeline.delete(text_bits_field)
    pipeline.delete(text_position_bits_field)
    for i in range(page_count):
        pipeline.setbit(image_bits_field, i, 0 if i in dirty_pages else 1)
        pipeline.setbit(text_bits_field, i, 0 if i in dirty_pages else 1)
        pipeline.setbit(text_position_bits_field, i, 0 if i in dirty_pages else 1)

    # Remove any existing page text
    pipeline.delete(redis_fields.page_text(doc_id))
    pipeline.delete(redis_fields.page_text_pdf(doc_id))

    # Execute the pipeline atomically
    pipeline.execute()


def write_cache(filename, cache):
    """Helper method to write a cache file."""
    mem_file = io.BytesIO()
    with gzip.open(mem_file, "wb") as zip_file:
        pickle.dump(cache, zip_file)

    storage.simple_upload(filename, mem_file.getvalue(), access=access_choices.PRIVATE)
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


def write_concatenated_text_file(doc_id, slug, access, page_jsons):
    """Assemble and write the concatenated text file given json pages"""
    concatenated_text = b"\n\n".join(
        [page["contents"].encode("utf-8") for page in page_jsons]
    )

    # Write the concatenated text file
    storage.simple_upload(
        path.text_path(doc_id, slug), concatenated_text, access=access
    )


def apply_modification(workspace, new_doc, context, modification):
    """Insert pages specified by a modification into a new document"""
    page_range = modification["page"]
    page_length = modification["page_length"]
    page_spec = modification["page_spec"]

    # Grab import document (from cache if possible)
    import_doc_id = modification.get("id", context["doc_id"])
    import_doc_slug = modification.get("slug", context["slug"])
    import_pdf_file = path.doc_path(import_doc_id, import_doc_slug)
    # pylint: disable=unnecessary-dunder-call
    import_doc = context["loaded_docs"].get(
        import_pdf_file,
        workspace.load_document_entirely(storage, import_pdf_file).__enter__(),
    )
    # Add to loaded docs cache
    context["loaded_docs"][import_pdf_file] = import_doc

    # Import the actual PDF pages
    new_doc.import_pages(import_doc, page_range, context["current_page_index"])

    # Extract the page text for the imported pages
    for i in range(page_length):
        # Get the page number
        if isinstance(page_spec[0], list):
            # Dealing with a page range.
            # Grab the first page and increment the range
            page = page_spec[0][0]
            end_page = page_spec[0][1]
            if page == end_page:
                # Pop out page range if at end
                page_spec = page_spec[1:]
            else:
                page_spec[0] = [page + 1, end_page]
        else:
            page = page_spec[0]
            page_spec = page_spec[1:]

        # Now, grab the json text paths of the affected document and
        # plan downloading the json text files in parallel
        json_file_path = path.json_text_path(import_doc_id, import_doc_slug)
        context["page_text_download_urls"].add(json_file_path)
        context["page_text_todo"].append(
            {
                "file_path": json_file_path,
                "page": page,
                "new_page": context["current_page_index"] + i,
            }
        )

    context["current_page_index"] += page_length


def apply_rotation_modification(new_doc, context, modification):
    """Apply rotations to a new document based on modifications"""
    page_length = modification["page_length"]
    modifiers = modification.get("modifications", [])

    # Check if rotation
    for modifier in modifiers:
        if modifier["type"] == "rotate":
            # Grab the 90-degree angle multiplier by which to rotate
            rotation_amount = ANGLE_TABLE.get(modifier.get("angle", ""), 0)
            if rotation_amount != 0:
                # Rotate all affected pages
                for i in range(
                    context["current_page_index"],
                    context["current_page_index"] + page_length,
                ):
                    page = new_doc.load_page(i)
                    new_doc.set_page_rotation(page, page.rotation + rotation_amount)

    context["current_page_index"] += page_length


def download_modification_page_text(context):
    """Download necessary page text for modifications in parallel"""
    page_text_json = []
    page_text_urls = list(context["page_text_download_urls"])
    logger.info("[DLMPT] %s %s", page_text_urls, storage.async_download(page_text_urls))
    page_text_download_files = [
        json.loads(contents) for contents in storage.async_download(page_text_urls)
    ]
    page_text_json_map = dict(zip(page_text_urls, page_text_download_files))

    for page_text_item in context["page_text_todo"]:
        # Construct the page text json from the downloaded page text
        page_text_json_file = page_text_json_map[page_text_item["file_path"]]
        page_text = page_text_json_file["pages"][page_text_item["page"]]
        page_text["page"] = page_text_item["new_page"]
        page_text_json.append(page_text)

    return page_text_json


def extract_text_position_for_page(pdf, doc_id, slug, page_number, access, in_memory):
    # If in-memory, the page number is always 0 (first and only overlay page)
    extract_page_number = 0 if in_memory else page_number
    page = pdf.pages[extract_page_number]
    words = [
        {
            "text": word["text"],
            "x1": float(word["x0"]) / float(page.width),
            "x2": float(word["x1"]) / float(page.width),
            "y1": float(word["top"]) / float(page.height),
            "y2": float(word["bottom"]) / float(page.height),
            "upright": word["upright"],
            "direction": word["direction"],
        }
        for word in page.extract_words(use_text_flow=True)
    ]
    # Write the json positional words file
    storage.simple_upload(
        path.page_text_position_path(doc_id, slug, page_number),
        json.dumps(words).encode("utf-8"),
        access=access,
    )


def graft_ocr_in_pdf(doc_id, slug, access):
    """Reinjects the OCR'd text-only PDFs back into the main PDF."""
    page_text_pdf_field = redis_fields.page_text_pdf(doc_id)
    redis_pdf_pages = REDIS.hkeys(page_text_pdf_field)
    doc_path = path.doc_path(doc_id, slug)

    # Load PDF in memory
    handler = StorageHandler(storage, doc_path, False, False, None, read_all=True)
    with Workspace() as workspace, workspace.load_document_custom(handler) as mem_pdf:
        mem_file = handler.mem_file  # Grab document as BytesIO instance

        # Graft all the pages
        grafter = graft.OcrGrafter(GraftContext(graft, mem_file, mem_pdf))
        for redis_page_key in redis_pdf_pages:
            page_number = int(redis_page_key)
            # Load overlay PDF in memory
            overlay_mem_file = io.BytesIO(
                REDIS.hget(page_text_pdf_field, redis_page_key)
            )
            grafter.graft_page(
                pageno=page_number,
                image=None,
                textpdf=overlay_mem_file,
                autorotate_correction=0,
            )

        # Overwrite source PDF
        with storage.open(doc_path, "wb", access=access) as output_file:
            grafter.output_file = output_file
            grafter.finalize()


def patch_partial_page_text(doc_id, slug, results):
    """Patch/assemble page text from a partial update."""
    with storage.open(path.json_text_path(doc_id, slug), "rb") as json_file:
        old_results = json.loads(json_file.read())

    for result in results["pages"]:
        page = result["page"]
        # Patch in the new page
        old_results["pages"][page] = result

    # Patch in the updated time
    old_results["updated"] = results["updated"]

    return old_results


@pubsub_function(REDIS, PAGE_CACHE_TOPIC)
def process_page_cache(data, _context=None):
    """Memoize the memory accesses of all the pages of a PDF in a cache."""
    # pylint: disable=too-many-locals
    data = get_pubsub_data(data)

    doc_id = data["doc_id"]
    slug = data["slug"]
    access = data.get("access", access_choices.PRIVATE)
    ocr_code = data.get("ocr_code", "eng")
    dirty = data.get("dirty")
    force_ocr = data.get("force_ocr", False)
    org_id = data.get("org_id", "")
    page_modification = data.get("page_modification", None)

    logger.info("[PROCESS PAGE CACHE] doc_id %s", doc_id)

    doc_path = path.doc_path(doc_id, slug)

    # Read the entire document into memory
    with Workspace() as workspace, StorageHandler(
        storage, doc_path, record=True, playback=False, cache=None, read_all=True
    ) as pdf_file, workspace.load_document_custom(pdf_file) as doc:
        # Load the final page to memoize all page accesses
        page_count = doc.page_count
        doc.load_page(page_count - 1)
        cached = pdf_file.cache

        # Set the file hash in Redis to go out with the next update
        REDIS.set(redis_fields.file_hash(doc_id), pdf_file.sha1)

        # Create an index file that stores the memory locations of each page of the
        # PDF file.
        write_cache(path.index_path(doc_id, slug), cached)

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
                            "ocr_code": ocr_code,
                            "pages": pages,
                            "partial": dirty,
                            "force_ocr": force_ocr,
                            "page_count": page_count,
                            "org_id": org_id,
                            "page_modification": page_modification,
                        }
                    ),
                )

        # Trigger image extraction tasks for each page
        if dirty:
            # If only dirty pages are flagged, process the relevant ones in batches
            dirty = sorted(dirty)
            for i in range(0, len(dirty), IMAGE_BATCH):
                pages = [dirty[j] for j in range(i, min(i + IMAGE_BATCH, len(dirty)))]
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
    ocr_code = data.get("ocr_code", "eng")
    page_modification = data.get("page_modification", None)

    logger.info("[PROCESS PDF] doc_id %s", doc_id)

    # Ensure PDF size is within the limit
    doc_path = path.doc_path(doc_id, slug)
    if storage.size(doc_path) > PDF_SIZE_LIMIT:
        # If not, remove the PDF
        storage.delete(path.path(doc_id))
        raise PdfSizeError()

    # files are always uploaded to S3 as private, set to public on S3
    # if uploaded publicly to DocumentCloud
    if access == access_choices.PUBLIC:
        storage.set_access([doc_path], access)

    # Extract the page count and store it in Redis
    page_count = extract_pagecount(doc_id, slug)
    initialize_redis_page_data(doc_id, page_count)

    # Update the model with the page count
    utils.send_update(REDIS, doc_id, {"page_count": page_count})

    # Kick off page cache processing
    publisher.publish(
        PAGE_CACHE_TOPIC,
        data=encode_pubsub_data(
            {
                "doc_id": doc_id,
                "slug": slug,
                "access": access,
                "ocr_code": ocr_code,
                "force_ocr": force_ocr,
                "page_modification": page_modification,
            }
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
            (
                image_width,
                max(round(img_buffer.height * (image_width / img_buffer.width)), 1),
            ),
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
    # pylint: disable=too-many-locals, too-many-statements, too-many-branches
    data = get_pubsub_data(data)

    doc_id = data["doc_id"]
    slug = data["slug"]
    access = data.get("access", access_choices.PRIVATE)
    ocr_code = data.get("ocr_code", "eng")
    doc_path = path.doc_path(doc_id, slug)
    page_numbers = data["pages"]  # The page numbers to extract
    partial = data["partial"]  # Whether it is a partial update (e.g. redaction) or not
    force_ocr = data["force_ocr"]
    page_modification = data.get("page_modification", None)

    logger.info(
        "[EXTRACT IMAGE] doc_id %s pages %s", doc_id, ",".join(map(str, page_numbers))
    )

    # Store a queue of pages to OCR/extract text positions to fill the batch
    ocr_queue = []
    text_position_queue = []

    def flush(queue, topic):
        if not queue:
            return

        logger.info("[EXTRACT IMAGE] flush: doc_id %s queue %s", doc_id, queue)
        # Trigger ocr pipeline
        publisher.publish(
            topic,
            data=encode_pubsub_data(
                {
                    "paths_and_numbers": queue,
                    "doc_id": doc_id,
                    "slug": slug,
                    "access": access,
                    "ocr_code": ocr_code,
                    "partial": partial,
                    "force_ocr": force_ocr,
                    "page_modification": page_modification,
                }
            ),
        )

        queue.clear()

    def check_and_flush(queue, topic, batch):
        if len(queue) >= batch:
            flush(queue, topic)

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
        # Iterate each page number
        for page_number in page_numbers:
            logger.info("[EXTRACT IMAGE] doc_id %s page_number %s", doc_id, page_number)
            # Only process if it has not processed previously
            large_image_path = path.page_image_path(
                doc_id, slug, page_number, IMAGE_WIDTHS[0][0]
            )
            page = None
            if not utils.page_extracted(REDIS, doc_id, page_number):
                # Extract the image if not already extracted
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
                # it's not a partial update or modification.
                if images_finished and not partial and page_modification is None:
                    update_pagespec(doc_id)

            if not utils.page_ocrd(REDIS, doc_id, page_number):
                # Extract page text if possible
                if page_modification is not None:
                    # In page modification mode, extract page text from the
                    # consolidated json file
                    with storage.open(
                        path.json_text_path(doc_id, slug), "rb"
                    ) as json_file:
                        json_text = json.loads(json_file.read())
                        text = json_text["pages"][page_number]["contents"]
                elif force_ocr:
                    text = None
                else:
                    if page is None:
                        page = doc.load_page(page_number)

                    text = page.text

                if text is not None and len(text.strip()) > 0:
                    # Page already has text inside
                    text_path = path.page_text_path(doc_id, slug, page_number)

                    write_text_file(text_path, text, access)
                    if page_modification is None:
                        utils.write_page_text(REDIS, doc_id, page_number, text, None)

                    # Decrement the texts remaining
                    utils.register_page_ocrd(REDIS, doc_id, page_number)

                    # Extract text position
                    text_position_queue.append(page_number)
                    check_and_flush(
                        text_position_queue,
                        TEXT_POSITION_EXTRACT_TOPIC,
                        TEXT_POSITION_BATCH,
                    )
                else:
                    # Prepare the image to be OCRd.
                    ocr_image_path = path.page_image_path(
                        doc_id, slug, page_number, IMAGE_WIDTHS[OCR_IMAGE_INDEX][0]
                    )
                    ocr_queue.append([page_number, ocr_image_path])
                    check_and_flush(ocr_queue, OCR_TOPIC, OCR_BATCH)

    flush(ocr_queue, OCR_TOPIC)
    flush(text_position_queue, TEXT_POSITION_EXTRACT_TOPIC)

    return "Ok"


@pubsub_function(REDIS, ASSEMBLE_TEXT_TOPIC)
def assemble_page_text(data, _context=None):
    """Assembles a text file with the doc text and merges the text pdf layers in."""
    data = get_pubsub_data(data)

    doc_id = data["doc_id"]
    slug = data["slug"]
    access = data.get("access", access_choices.PRIVATE)
    partial = data["partial"]  # Whether it is a partial update (e.g. redaction) or not

    logger.info("[ASSEMBLE TEXT] doc_id %s", doc_id)

    # Reinject OCR layer into PDF
    try:
        graft_ocr_in_pdf(doc_id, slug, access)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[Grafting doc_id %s failed]", doc_id, exc_info=exc)

    # Remove the in-memory text PDFs from Redis
    # (now that the PDF is grafted, OCR does not have to run if reprocessed)
    REDIS.delete(redis_fields.page_text_pdf(doc_id))

    results = utils.get_all_page_text(REDIS, doc_id)

    if partial:
        # Patch the old results in if it's a partial update
        results = patch_partial_page_text(doc_id, slug, results)

    # Compile and write concatenated text only outside of import mode
    # (we don't want to overwrite the previous file)
    write_concatenated_text_file(doc_id, slug, access, results["pages"])

    # Write the json text file
    storage.simple_upload(
        path.json_text_path(doc_id, slug),
        json.dumps(results).encode("utf-8"),
        access=access,
    )

    # All done processing the doc now
    utils.send_complete(REDIS, doc_id)

    return "Ok"


@pubsub_function(REDIS, TEXT_POSITION_EXTRACT_TOPIC)
def extract_text_position(data, _context=None):
    """Extracts text position files for each page of the document."""
    # pylint: disable=too-many-locals, too-many-statements
    data = get_pubsub_data(data)

    doc_id = data["doc_id"]
    slug = data["slug"]
    access = data.get("access", access_choices.PRIVATE)
    page_modification = data.get("page_modification", None)
    in_memory = data.get("in_memory", False)
    page_numbers = data["paths_and_numbers"]  # The page numbers to extract
    partial = data["partial"]  # Whether it is a partial update (e.g. redaction) or not
    doc_path = path.doc_path(doc_id, slug)

    logger.info(
        "[EXTRACT TEXT POSITION] doc_id %s page_numbers %s", doc_id, page_numbers
    )

    page_text_pdf_field = redis_fields.page_text_pdf(doc_id)

    # Grab the PDF
    errored = False
    pdf = None
    if not in_memory:
        # If not using in-memory Redis PDFs, read the whole doc file into memory
        with storage.open(doc_path, "rb") as doc_file:
            contents = doc_file.read()
            mem_file = io.BytesIO(contents)
        try:
            pdf = pdfplumber.open(mem_file)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception(
                "[Opening pdfplumber doc_id %s failed]", doc_id, exc_info=exc
            )
            errored = True

    # Write all the text positions to file

    # Go through each page
    for page_number in page_numbers:
        logger.info(
            "[EXTRACT TEXT POSITION] doc_id %s page_number %s", doc_id, page_number
        )
        if in_memory:
            # If in-memory, use the Redis overlay PDF
            errored = False
            overlay_mem_file = io.BytesIO(
                REDIS.hget(page_text_pdf_field, f"{page_number}")
            )
            try:
                pdf = pdfplumber.open(overlay_mem_file)
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception(
                    "[Opening pdfplumber doc_id %s failed]", doc_id, exc_info=exc
                )
                errored = True

        if not errored:
            try:
                extract_text_position_for_page(
                    pdf, doc_id, slug, page_number, access, in_memory
                )
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception(
                    "[Extracting pdfplumber doc_id %s page %d failed]",
                    doc_id,
                    page_number,
                    exc_info=exc,
                )

        if in_memory and pdf:
            # Close pdfplumber on the overlay pdf
            pdf.close()

        # Check if all text positions have been extracted
        text_positions_finished = utils.register_text_position_extracted(
            REDIS, doc_id, page_number
        )
        logger.info(
            "[EXTRACT TEXT POSITION] doc_id %s finished %s",
            doc_id,
            text_positions_finished,
        )
        if text_positions_finished:
            if page_modification is not None:
                # Normally, processing entails assembling text once
                # finished. In page modification mode, the consolidated
                # json has already been created, so now we defer to
                # finishing steps.
                raw_pagespec = get_redis_pagespec(doc_id)
                pagespec = crunch_collection(raw_pagespec)
                filehash = utils.pop_file_hash(REDIS, doc_id)
                utils.send_modification_post_processing(
                    REDIS,
                    doc_id,
                    {
                        "modifications": page_modification["modifications"],
                        "pagespec": pagespec,
                        "filehash": filehash,
                    },
                )
            else:
                # Move on to assembling/grafting the text back into the pdf
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

    if not in_memory and pdf:
        # Close pdfplumber
        pdf.close()

    return "Ok"


@pubsub_function(REDIS, REDACT_TOPIC)
def redact_doc(data, _context=None):
    """Redacts a document and reprocesses altered pages."""
    data = get_pubsub_data(data)

    doc_id = data["doc_id"]
    slug = data["slug"]
    access = data.get("access", access_choices.PRIVATE)
    redactions = data["redactions"]
    ocr_code = data.get("ocr_code", "eng")

    logger.info(
        "[REDACT DOC] doc_id %s redactions %s",
        doc_id,
        ",".join([str(r["page_number"]) for r in redactions]),
    )

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
                "ocr_code": ocr_code,
                "dirty": dirty_pages_list,
            }
        ),
    )

    return "Ok"


@pubsub_function(REDIS, MODIFY_TOPIC)
def modify_doc(data, _context=None):
    """Applies page modifications to a document."""
    data = get_pubsub_data(data)
    doc_id = data["doc_id"]
    slug = data["slug"]
    access = data.get("access", access_choices.PRIVATE)
    modifications = data["modifications"]["data"]
    backup_modifications = copy.deepcopy(modifications)

    logger.info(
        "[MODIFY DOC] doc_id %s modifications %s", doc_id, json.dumps(modifications)
    )

    # Construct modified pdf
    modify_context = {
        "doc_id": doc_id,
        "slug": slug,
        "loaded_docs": {},  # Cache doc handles so docs are never loaded twice
        "current_page_index": 0,
        "page_text_todo": [],
        "page_text_download_urls": set(),
    }

    def close_all_docs():
        for doc in modify_context["loaded_docs"].values():
            doc.close()

    with Workspace() as workspace:
        new_doc = workspace.new_document()
        # Apply each modification to create a new document
        for modification in modifications:
            apply_modification(workspace, new_doc, modify_context, modification)

        # Close all open handles
        close_all_docs()

        # Download all the page text in parallel
        page_text_json = download_modification_page_text(modify_context)

        # Run a second pass through all modifications to perform rotations.
        modify_context["current_page_index"] = 0
        for modification in modifications:
            apply_rotation_modification(new_doc, modify_context, modification)

        # Overwrite PDF file with newly constructed modified PDF file
        doc_path = path.doc_path(doc_id, slug)
        new_doc.save(storage, doc_path, access)

        # Assemble full json structure and write to file
        full_page_text_json = {"updated": millis(), "pages": page_text_json}
        page_text_json_path = path.json_text_path(doc_id, slug)
        storage.simple_upload(
            page_text_json_path,
            json.dumps(full_page_text_json).encode("utf-8"),
            access=access,
        )

        # Write concatenated text file as well
        write_concatenated_text_file(doc_id, slug, access, page_text_json)

        # Delete old page files
        storage.delete(path.pages_path(doc_id))

        # Kick off processing tasks to
        #  * extract new index file for PDF and ensure PDF file is within size limits
        #  * reextract all image files and derive page spec
        #  * create text files from consolidated page text json
        #  * copy temporary directory into original directory
        utils.clean_up(REDIS, doc_id)
        utils.initialize(REDIS, doc_id)
        publisher.publish(
            PDF_PROCESS_TOPIC,
            data=encode_pubsub_data(
                {
                    "doc_id": doc_id,
                    "slug": slug,
                    "access": access,
                    "page_modification": {
                        "page_text_json_file": page_text_json_path,
                        "modifications": backup_modifications,
                    },
                }
            ),
        )

    return "Ok"


@pubsub_function(REDIS, START_IMPORT_TOPIC)
def start_import(data, _context=None):
    """Reads in an org's import CSV and starts the import process."""
    data = get_pubsub_data(data)
    org_id = data["org_id"]
    offset = data.get("offset", 0)
    num_docs = data.get("num_docs", 0)

    logger.info(
        "[START IMPORT] org_id %s offset %d num_docs %d", org_id, offset, num_docs
    )

    with storage.open(path.import_org_csv(org_id), "r") as csvfile:
        csvreader = csv.reader(csvfile)
        next(csvreader)  # discard headers

        doc_ids = []
        for row in itertools.islice(csvreader, offset, offset + IMPORT_DOCS_BATCH):
            # Pull the doc id (1st column), slug (7th column), and access (4th column)
            doc_ids.append((row[0], row[6], row[3]))

    # Initialize Redis on first invocation
    if offset == 0:
        with storage.open(path.import_org_csv(org_id), "r") as csvfile:
            # Getting total number of docs requires reading the whole file
            # rather than a slice. This could be done without a CSV file reader
            # but to prevent any strange behavior the same approach is used.
            csvreader = csv.reader(csvfile)
            next(csvreader)  # discard headers
            num_docs = sum(1 for _ in csvreader)
        REDIS.set(redis_fields.import_docs_remaining(org_id), num_docs)

    for doc_id, slug, access in doc_ids:
        logger.info("[START IMPORT] org_id %s doc_id %s slug %s", org_id, doc_id, slug)
        publisher.publish(
            IMPORT_DOCUMENT_TOPIC,
            encode_pubsub_data(
                {
                    "org_id": org_id,
                    "doc_id": doc_id,
                    "slug": slug,
                    # 4 is public, 8,9 are pre/post moderated which act as public
                    "public": access in ("4", "8", "9"),
                }
            ),
        )

    if offset + IMPORT_DOCS_BATCH < num_docs:
        # More docs remaining
        publisher.publish(
            START_IMPORT_TOPIC,
            encode_pubsub_data(
                {
                    "org_id": org_id,
                    "offset": offset + IMPORT_DOCS_BATCH,
                    "num_docs": num_docs,
                }
            ),
        )

    return "Ok"


@pubsub_function_import(REDIS, FINISH_IMPORT_TOPIC)
def import_document(data, _context=None):
    # pylint: disable=too-many-locals, too-many-statements
    """All-in-one function that handles the import process for a single document."""
    data = get_pubsub_data(data)
    org_id = data["org_id"]
    doc_id = data["doc_id"]
    slug = data["slug"]
    public = data.get("public")

    logger.info(
        "[IMPORT DOCUMENT] org_id %s doc_id %s slug %s public %s",
        org_id,
        doc_id,
        slug,
        public,
    )

    # STEP 1: Grab page count and write index file for caching PDF memory accesses
    logger.info("[PAGE COUNT] org_id %s doc_id %s slug %s", org_id, doc_id, slug)
    doc_path = path.doc_path(doc_id, slug)
    try:
        with Workspace() as workspace, StorageHandler(
            storage, doc_path, record=True, playback=False, cache=None, read_all=True
        ) as pdf_file, workspace.load_document_custom(pdf_file) as doc:
            # Load the final page to memoize all page accesses
            page_count = doc.page_count
            doc.load_page(page_count - 1)
            cached = pdf_file.cache

            # Write the index file
            # simple retry for s3 errors
            for retry in range(3):
                try:
                    write_cache(path.index_path(doc_id, slug), cached)
                    break
                except ClientError as exc:
                    # sleep 1-2 seconds, 2-4 second between retries
                    logger.info(
                        "[WRITE CACHE] org_id %s doc_id %s exc %s retry %s",
                        org_id,
                        doc_id,
                        exc,
                        retry,
                    )
                    if retry == 2:
                        raise exc
                    time.sleep(randint(2**retry, 2 ** (retry + 1)))
    except (ValueError, AssertionError, ClientError):
        # document was not found
        logger.info(
            "[IMPORT DOCUMENT] DOCUMENT NOT FOUND org_id %s doc_id %s slug %s",
            org_id,
            doc_id,
            slug,
        )
        REDIS.hset(redis_fields.import_pagespecs(org_id), f"{doc_id}", "")
        publisher.publish(
            FINISH_IMPORT_TOPIC,
            encode_pubsub_data({"org_id": org_id, "doc_id": doc_id, "slug": slug}),
        )
        return

    # STEP 2: Grab all pagespecs from fully read PDF file
    # (we could combine with previous step, but memoizing all accesses could be costly)
    logger.info("[COLLECT PAGESPECS] org_id %s doc_id %s slug %s", org_id, doc_id, slug)
    pagespec = collections.defaultdict(list)
    try:
        with Workspace() as workspace, StorageHandler(
            storage, doc_path, record=False, playback=False, cache=None, read_all=True
        ) as pdf_file, workspace.load_document_custom(pdf_file) as doc:
            for page_number in range(page_count):
                page = doc.load_page(page_number)
                # Grab page dimensions
                width, height = page.width, page.height
                page_dimension = f"{width}x{height}"

                # Assemble page spec piece-by-piece
                pagespec[page_dimension].append(page_number)
    except (ValueError, AssertionError):
        # document is corrupt
        logger.info(
            "[IMPORT DOCUMENT] DOCUMENT NOT FOUND org_id %s doc_id %s slug %s",
            org_id,
            doc_id,
            slug,
        )
        REDIS.hset(redis_fields.import_pagespecs(org_id), f"{doc_id}", "")
        publisher.publish(
            FINISH_IMPORT_TOPIC,
            encode_pubsub_data({"org_id": org_id, "doc_id": doc_id, "slug": slug}),
        )
        return

    # STEP 3: Crunch pagespec down and store in Redis
    logger.info("[STORE PAGESPECS] org_id %s doc_id %s slug %s", org_id, doc_id, slug)
    crunched_pagespec = crunch_collection(pagespec)
    REDIS.hset(redis_fields.import_pagespecs(org_id), f"{doc_id}", crunched_pagespec)

    # STEP 4: grab all page texts in batches, asynchronously
    logger.info(
        "[DOWNLOAD PAGE TEXTS] org_id %s doc_id %s slug %s", org_id, doc_id, slug
    )
    page_texts = []
    for i in range(0, page_count, TEXT_READ_BATCH):
        pages = list(range(i, min(i + TEXT_READ_BATCH, page_count)))
        file_names = [path.page_text_path(doc_id, slug, p) for p in pages]
        page_texts.extend(storage.async_download(file_names))

    # STEP 5: assemble page texts into JSON
    logger.info(
        "[ASSEMBLE PAGE TEXT] org_id %s doc_id %s slug %s", org_id, doc_id, slug
    )

    # Annotate the results with the current timestamp
    current_millis = millis()

    page_texts_json_pages = [
        {
            "page": page_number,
            "contents": page_texts[page_number].decode("utf8"),
            "ocr": IMPORT_OCR_VERSION,
            "updated": current_millis,
        }
        for page_number in range(page_count)
    ]
    page_texts_json = {
        "updated": current_millis,
        "pages": page_texts_json_pages,
        "is_import": True,
    }

    # Write the json text file
    # Seeing occasional S3 slow down errors here
    # do a simple retry with exponential back off
    for retry in range(3):
        try:
            storage.simple_upload(
                path.json_text_path(doc_id, slug),
                json.dumps(page_texts_json).encode("utf-8"),
                access=access_choices.PUBLIC if public else access_choices.PRIVATE,
            )
            break
        except ClientError as exc:
            # sleep 1-2 seconds, 2-4 second, 4-8 seconds between retries
            logger.info(
                "[UPLOAD JSON TEXT] org_id %s doc_id %s exc %s retry %s",
                org_id,
                doc_id,
                exc,
                retry,
            )
            if retry < 2:
                time.sleep(randint(2**retry, 2 ** (retry + 1)))
    else:
        # Did not succeed after 3 retires, just skip
        logger.info("[UPLOAD JSON TEXT] failed - org_id %s doc_id %s", org_id, doc_id)

    # STEP 6: Call finish import
    publisher.publish(
        FINISH_IMPORT_TOPIC,
        encode_pubsub_data({"org_id": org_id, "doc_id": doc_id, "slug": slug}),
    )


@pubsub_function(REDIS, FINISH_IMPORT_TOPIC, skip_processing_check=True)
def finish_import(data, _context=None):
    """Finishes off the import process"""
    data = get_pubsub_data(data)
    org_id = data["org_id"]
    doc_id = data["doc_id"]

    import_docs_remaining = REDIS.decr(redis_fields.import_docs_remaining(org_id))

    logger.info(
        "[FINISH IMPORT] org_id %s doc_id %s import_docs_remaining %s",
        org_id,
        doc_id,
        import_docs_remaining,
    )

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
                pagespec = pagespecs.get(doc_id, "")
                # Add pagespec to each row
                rows.append(row + [pagespec])
                logger.info(
                    "[FINISH IMPORT] READING CSV org_id %s doc_id %s pagespec %s",
                    org_id,
                    doc_id,
                    pagespec,
                )

        # Write the new pagespec-enhanced CSV
        with storage.open(path.import_org_pagespec_csv(org_id), "w") as new_csv_file:
            csvwriter = csv.writer(new_csv_file, quoting=csv.QUOTE_ALL)
            for row in rows:
                csvwriter.writerow(row)
                logger.info("[FINISH IMPORT] WRITING CSV row %s", row)

        # Clean up Redis
        REDIS.delete(
            redis_fields.import_docs_remaining(org_id),
            redis_fields.import_pagespecs(org_id),
        )
