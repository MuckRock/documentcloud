"""
Helper functions to perform common serverless operations.
"""

# Standard Library
import json
import logging
import sys
import time
from urllib.parse import urljoin

# Third Party
import environ
import furl
import redis as _redis
import requests

# Local
from .. import redis_fields

env = environ.Env()

# Common environment variables
API_CALLBACK = env.str("API_CALLBACK")
PROCESSING_TOKEN = env.str("PROCESSING_TOKEN")
REDIS_URL = furl.furl(env.str("REDIS_PROCESSING_URL"))
REDIS_PASSWORD = env.str("REDIS_PROCESSING_PASSWORD")
REDIS_SOCKET_TIMEOUT = env.int("REDIS_SOCKET_TIMEOUT", default=10)
REDIS_SOCKET_CONNECT_TIMEOUT = env.int("REDIS_SOCKET_CONNECT_TIMEOUT", default=10)
REDIS_HEALTH_CHECK_INTERVAL = env.int("REDIS_HEALTH_CHECK_INTERVAL", default=10)


def get_redis():
    """Opens a connection to Redis and returns it"""
    kwargs = {
        "host": REDIS_URL.host,
        "port": REDIS_URL.port,
        "db": 0,
        "socket_timeout": REDIS_SOCKET_TIMEOUT,
        "socket_keepalive": True,
        "socket_connect_timeout": REDIS_SOCKET_CONNECT_TIMEOUT,
        "retry_on_timeout": True,
        "health_check_interval": REDIS_HEALTH_CHECK_INTERVAL,
    }

    # Empty string should open a Redis connection without password
    if REDIS_PASSWORD and not REDIS_PASSWORD.isspace():
        kwargs["password"] = REDIS_PASSWORD

    return _redis.Redis(**kwargs)


def send_update(redis, doc_id, json_):
    """Sends an update to the API server specified as JSON"""
    if not still_processing(redis, doc_id):
        return

    # Add file hash data in if present
    file_hash = redis.get(redis_fields.file_hash(doc_id))
    if file_hash:
        json_["file_hash"] = file_hash.decode("ascii")  # hex string
        redis.delete(redis_fields.file_hash(doc_id))

    requests.patch(
        urljoin(API_CALLBACK, f"documents/{doc_id}/"),
        json=json_,
        headers={"Authorization": f"processing-token {PROCESSING_TOKEN}"},
    )


def send_complete(redis, doc_id):
    """Sends an update to the API server that processing is complete"""
    if not still_processing(redis, doc_id):
        return

    send_update(redis, doc_id, {"status": "success"})

    # Clean out Redis
    clean_up(redis, doc_id)


def send_error(redis, doc_id, message, fatal=False):
    """Sends an error to the API server specified as a string message"""
    if doc_id and not still_processing(redis, doc_id):
        return

    # Send the error to the server
    if doc_id:
        requests.post(
            urljoin(API_CALLBACK, f"documents/{doc_id}/errors/"),
            json={"message": message},
            headers={"Authorization": f"processing-token {PROCESSING_TOKEN}"},
        )

        # pylint: disable=bare-except
        try:
            # Try to log additional Redis information if possible
            message += (
                f"\n\nPage count: {redis.get(redis_fields.page_count(doc_id))}"
                f"\nImages remaining: "
                f"{redis.get(redis_fields.images_remaining(doc_id))}"
                f"\nTexts remaining: {redis.get(redis_fields.texts_remaining(doc_id))}"
            )
        except:
            pass

    # Log the error depending on its severity
    if fatal:
        logging.error(message, exc_info=sys.exc_info())
    else:
        logging.warning(message, exc_info=sys.exc_info())

    # Clean out Redis
    if doc_id:
        clean_up(redis, doc_id)


def initialize(redis, doc_id):
    """Sets up Redis for processing"""
    redis.set(redis_fields.is_running(doc_id), 1)


def still_processing(redis, doc_id):
    """Returns whether the doc_id is still processing"""
    return redis.get(redis_fields.is_running(doc_id)) == b"1"


def clean_up(redis, doc_id):
    """Removes all keys associated with a document id in redis"""

    dimensions_field = redis_fields.dimensions(doc_id)

    def remove_all(pipeline):
        # Remove all simple fields
        pipeline.delete(
            redis_fields.images_remaining(doc_id),
            redis_fields.texts_remaining(doc_id),
            redis_fields.page_count(doc_id),
            redis_fields.is_running(doc_id),
            redis_fields.image_bits(doc_id),
            redis_fields.text_bits(doc_id),
            redis_fields.page_text(doc_id),
        )

        # Remove any existing dimensions that may be lingering
        existing_dimensions = pipeline.smembers(dimensions_field)
        if existing_dimensions is not None:
            for dimension in existing_dimensions:
                pipeline.delete(redis_fields.page_dimension(doc_id, dimension))
        pipeline.delete(dimensions_field)

    redis.transaction(remove_all, dimensions_field)


def page_extracted(redis, doc_id, page_number):
    """Returns if the page has already had its image extracted."""
    image_bits_field = redis_fields.image_bits(doc_id)
    return redis.getbit(image_bits_field, page_number) != 0


def page_ocrd(redis, doc_id, page_number):
    """Returns if the page has already been OCRd."""
    text_bits_field = redis_fields.text_bits(doc_id)
    return redis.getbit(text_bits_field, page_number) != 0


def register_page_task(redis, page_number, remaining_field, bits_field):
    """Registers a generic Redis page task, returning the remaining count."""

    # Start a pipeline to atomically decrement remaining and toggle page
    def decrement_remaining(pipeline):
        existing_value = pipeline.getbit(bits_field, page_number)
        if existing_value == 1:
            # Page has already been extracted
            pipeline.multi()
            pipeline.get(remaining_field)
            return

        pipeline.multi()
        pipeline.decr(remaining_field)
        pipeline.setbit(bits_field, page_number, 1)

    return redis.transaction(decrement_remaining, bits_field)[0]


def register_page_extracted(redis, doc_id, page_number):
    """Register a single page as being extracted. Return true if all done."""
    # Decrement the images remaining
    images_remaining = register_page_task(
        redis,
        page_number,
        redis_fields.images_remaining(doc_id),
        redis_fields.image_bits(doc_id),
    )
    return images_remaining == 0


def register_page_ocrd(redis, doc_id, page_number):
    """Register a single page as being OCRd. Return true if all done."""
    # Decrement the texts remaining
    texts_remaining = register_page_task(
        redis,
        page_number,
        redis_fields.texts_remaining(doc_id),
        redis_fields.text_bits(doc_id),
    )
    return texts_remaining == 0


def write_page_text(redis, doc_id, page_number, page_text, ocr):
    """Write page text to Redis."""
    redis.hset(
        redis_fields.page_text(doc_id),
        f"{page_number}",
        json.dumps({"text": page_text, "ocr": ocr}),
    )


def get_all_page_text(redis, doc_id, is_import=False):
    """Read all the page text stored in Redis."""
    page_text_map = redis.hgetall(redis_fields.page_text(doc_id))
    pages = sorted([int(page_number) for page_number in page_text_map.keys()])

    # Annotate the results with the current timestamp
    current_millis = int(round(time.time() * 1000))

    def get_page(page_number):
        """Helper function to return a page from Redis's result set."""
        contents = json.loads(page_text_map[f"{page_number}".encode("utf-8")])
        return {
            "page": page_number,
            "contents": contents["text"],
            "ocr": contents["ocr"],
            "updated": current_millis,
        }

    results = [get_page(page_number) for page_number in pages]
    response = {"updated": current_millis, "pages": results}
    if is_import:
        response["is_import"] = True
    return response
