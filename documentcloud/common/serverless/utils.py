"""
Helper functions to perform common serverless operations.
"""

# Standard Library
import json
import logging
import time
from urllib.parse import urljoin

# Third Party
import environ
import furl
import redis as _redis
import requests
from redis.lock import Lock
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Local
from .. import redis_fields
from ..environment import encode_pubsub_data, publisher

env = environ.Env()

# pylint: disable=import-error

if not env.str("ENVIRONMENT").startswith("local"):
    # in production, log errors to sentry
    # must capture explicitly instead of using logging integration due
    # to using pebble and multiprocessing - logging integration does
    # not work across process boundary
    # see https://github.com/getsentry/raven-python/issues/1110#issuecomment-688923571
    # Third Party
    from sentry_sdk import capture_exception, capture_message, flush
else:

    # locally reraise the exception for debuggin purposes
    def capture_exception(exc):
        raise exc

    def capture_message(_msg):
        pass

    def flush():
        pass


# Common environment variables
API_CALLBACK = env.str("API_CALLBACK")
PROCESSING_TOKEN = env.str("PROCESSING_TOKEN")
REDIS_URL = furl.furl(env.str("REDIS_PROCESSING_URL"))
REDIS_PASSWORD = env.str("REDIS_PROCESSING_PASSWORD")
REDIS_SOCKET_TIMEOUT = env.int("REDIS_SOCKET_TIMEOUT", default=10)
REDIS_SOCKET_CONNECT_TIMEOUT = env.int("REDIS_SOCKET_CONNECT_TIMEOUT", default=10)
REDIS_HEALTH_CHECK_INTERVAL = env.int("REDIS_HEALTH_CHECK_INTERVAL", default=10)
RETRY_ERROR_TOPIC = publisher.topic_path(
    "documentcloud", env.str("RETRY_ERROR_TOPIC", default="retry-error-topic")
)
REDIS_TTL = env.int("REDIS_TTL", default=86400)


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


def pop_file_hash(redis, doc_id):
    """Extracts the file hash and removes from redis"""
    file_hash = redis.get(redis_fields.file_hash(doc_id))
    if file_hash:
        decoded_hash = file_hash.decode("ascii")  # hex string
        redis.delete(redis_fields.file_hash(doc_id))
        return decoded_hash
    return None


def request(redis, method, url, json_):
    """Request wrapper to handle errors"""
    logging.info("[UTILS REQUEST] method: %s url: %s json: %s", method, url, json_)
    response = requests.request(
        method,
        urljoin(API_CALLBACK, url),
        json=json_,
        timeout=30,
        headers={"Authorization": f"processing-token {PROCESSING_TOKEN}"},
    )
    if 400 <= response.status_code < 500:
        # client error, log and fix if necessary
        logging.error(response.text)
        capture_message(response.text)
    elif response.status_code >= 500:
        # server error, store for retry
        redis.lpush(
            redis_fields.error_retry_queue(),
            json.dumps({"method": method, "url": url, "json": json_}),
        )
        logging.info(
            "[UTILS REQUEST] queueing for retry: method: %s url: %s json: %s",
            method,
            url,
            json_,
        )
        logging.error(response.text)
        capture_message(response.text)
    elif (
        200 <= response.status_code < 300
        and not Lock(redis, redis_fields.error_retry_lock()).locked()
        and redis.llen(redis_fields.error_retry_queue()) > 0
    ):
        # success, retry error queue if populated
        publisher.publish(RETRY_ERROR_TOPIC, encode_pubsub_data({}))

    return response


def send_update(redis, doc_id, json_):
    """Sends an update to the API server specified as JSON"""
    if not still_processing(redis, doc_id):
        return

    # Add file hash data in if present
    file_hash = pop_file_hash(redis, doc_id)
    if file_hash:
        json_["file_hash"] = file_hash

    request(redis, "patch", f"documents/{doc_id}/", json_)


def send_complete(redis, doc_id):
    """Sends an update to the API server that processing is complete"""
    if not still_processing(redis, doc_id):
        return

    send_update(redis, doc_id, {"status": "success"})

    # Clean out Redis
    clean_up(redis, doc_id)


def send_error(redis, doc_id, exc=None, message=None):
    """Sends an error to the API server specified as a string message"""
    if doc_id and not still_processing(redis, doc_id):
        return

    if message is None:
        message = str(exc)

    # Send the error to the server
    if doc_id:
        request(redis, "post", f"documents/{doc_id}/errors/", {"message": message})

    if exc is not None:
        logging.error(message, exc_info=exc)
        capture_exception(exc)
        flush()
    else:
        logging.error(message)
        capture_message(message)

    # Clean out Redis
    if doc_id:
        clean_up(redis, doc_id)


def send_modification_post_processing(redis, doc_id, json_):
    """Send update to trigger page modification post-processing"""
    if not still_processing(redis, doc_id):
        return

    request(redis, "post", f"documents/{doc_id}/modifications/post_process/", json_)

    # Clean out Redis
    clean_up(redis, doc_id)


def initialize(redis, doc_id):
    """Sets up Redis for processing"""
    redis.set(redis_fields.is_running(doc_id), 1, ex=REDIS_TTL)


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
            redis_fields.text_positions_remaining(doc_id),
            redis_fields.page_count(doc_id),
            redis_fields.is_running(doc_id),
            redis_fields.image_bits(doc_id),
            redis_fields.text_bits(doc_id),
            redis_fields.text_position_bits(doc_id),
            redis_fields.page_text(doc_id),
            redis_fields.page_text_pdf(doc_id),
        )

        # Remove any existing dimensions that may be lingering
        existing_dimensions = pipeline.smembers(dimensions_field)
        if existing_dimensions is not None:
            for dimension in existing_dimensions:
                dimension = dimension.decode("utf8")
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


def register_text_position_extracted(redis, doc_id, page_number):
    """Register a single page text position extraction. Return true if all done."""
    # Decrement the texts remaining
    text_positions_remaining = register_page_task(
        redis,
        page_number,
        redis_fields.text_positions_remaining(doc_id),
        redis_fields.text_position_bits(doc_id),
    )
    return text_positions_remaining == 0


def write_page_text(redis, doc_id, page_number, page_text, ocr, ocr_code="eng"):
    """Write page text to Redis."""
    redis.hset(
        redis_fields.page_text(doc_id),
        f"{page_number}",
        json.dumps({"text": page_text, "ocr": ocr, "ocr_code": ocr_code}),
    )
    redis.expire(redis_fields.page_text(doc_id), REDIS_TTL)


def write_page_text_pdf(redis, doc_id, page_number, page_text_pdf_contents):
    """Write text-only pdf file to Redis."""
    redis.hset(
        redis_fields.page_text_pdf(doc_id), f"{page_number}", page_text_pdf_contents
    )
    redis.expire(redis_fields.page_text_pdf(doc_id), REDIS_TTL)


def get_all_page_text(redis, doc_id):
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
            "lang": contents.get("lang", "eng"),
            "updated": current_millis,
        }

    results = [get_page(page_number) for page_number in pages]
    response = {"updated": current_millis, "pages": results}
    return response


def initialize_text_positions(redis, doc_id, page_count):
    """Initialize text position data in Redis."""
    pipeline = redis.pipeline()
    pipeline.set(
        redis_fields.text_positions_remaining(doc_id), page_count, ex=REDIS_TTL
    )
    text_position_bit_field = redis_fields.text_position_bits(doc_id)
    pipeline.delete(text_position_bit_field)
    pipeline.setbit(text_position_bit_field, page_count - 1, 0)
    pipeline.expire(text_position_bit_field, REDIS_TTL)
    pipeline.execute()
