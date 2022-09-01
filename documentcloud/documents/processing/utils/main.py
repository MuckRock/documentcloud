# Standard Library
import json
import logging
import sys
import time
from itertools import zip_longest

# Third Party
import environ
from redis.exceptions import LockError, RedisError

env = environ.Env()
logger = logging.getLogger(__name__)

# pylint: disable=import-error

# Imports based on execution context
if env.str("ENVIRONMENT").startswith("local"):
    # DocumentCloud
    from documentcloud.common import redis_fields
    from documentcloud.common.environment import (
        encode_pubsub_data,
        encode_response,
        get_http_data,
        processing_auth,
        publisher,
    )
    from documentcloud.common.serverless import utils
    from documentcloud.common.serverless.error_handling import pubsub_function
else:
    # Third Party
    # only initialize sentry on serverless
    import sentry_sdk
    from common import redis_fields
    from common.environment import (
        encode_pubsub_data,
        encode_response,
        get_http_data,
        processing_auth,
        publisher,
    )
    from common.serverless import utils
    from common.serverless.error_handling import pubsub_function
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=env("SENTRY_DSN"), integrations=[AwsLambdaIntegration(), RedisIntegration()]
    )

REDIS = utils.get_redis()

# Topic names for the messaging queue
PDF_PROCESS_TOPIC = publisher.topic_path(
    "documentcloud", env.str("PDF_PROCESS_TOPIC", default="pdf-process")
)
DOCUMENT_CONVERT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("DOCUMENT_CONVERT_TOPIC", default="document-convert")
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
SIDEKICK_PREPROCESS_TOPIC = publisher.topic_path(
    "documentcloud",
    env.str("SIDEKICK_PREPROCESS_TOPIC", default="sidekick-preprocess-topic"),
)
RETRY_ERROR_TOPIC = publisher.topic_path(
    "documentcloud", env.str("RETRY_ERROR_TOPIC", default="retry-error-topic")
)


@processing_auth
def process_doc(request, _context=None):
    """Central command to run processing on a doc"""
    data = get_http_data(request)
    doc_id = data["doc_id"]
    job_type = data["method"]
    extension = data.get("extension", "pdf").lower()

    # Initialize the processing environment
    utils.initialize(REDIS, doc_id)

    # Launch PDF processing via pubsub
    if job_type == "process_pdf":
        if extension == "pdf":
            publisher.publish(PDF_PROCESS_TOPIC, data=encode_pubsub_data(data))
        else:
            # Non-PDF files require conversion first
            publisher.publish(DOCUMENT_CONVERT_TOPIC, data=encode_pubsub_data(data))
    elif job_type == "redact_doc":
        publisher.publish(REDACT_TOPIC, data=encode_pubsub_data(data))
    elif job_type == "modify_doc":
        publisher.publish(MODIFY_TOPIC, data=encode_pubsub_data(data))
    elif job_type == "cancel_doc_processing":
        utils.clean_up(REDIS, doc_id)
    else:
        logger.error(
            "Invalid doc processing type: %s", job_type, exc_info=sys.exc_info()
        )
        return "Error"

    return encode_response("Ok")


def grouper(iterable, num, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * num
    return zip_longest(*args, fillvalue=fillvalue)


@processing_auth
def get_progress(request, _context=None):
    """Get progress information from redis"""
    data = get_http_data(request)
    doc_id = data.get("doc_id")
    doc_ids = data.get("doc_ids")

    # doc_ids could still be specified as empty list, so check for None
    if doc_ids is None:
        doc_ids = [doc_id]

    response = []

    try:
        redis_progress_fields = []
        for doc_id in doc_ids:
            redis_progress_fields.append(redis_fields.images_remaining(doc_id))
            redis_progress_fields.append(redis_fields.texts_remaining(doc_id))
            redis_progress_fields.append(redis_fields.text_positions_remaining(doc_id))
            redis_progress_fields.append(redis_fields.page_count(doc_id))
        data = grouper(
            (int(i) if i is not None else i for i in REDIS.mget(redis_progress_fields)),
            4,
        )
        for doc_id, (images, texts, text_positions, pages) in zip(doc_ids, data):
            response.append(
                {
                    "doc_id": doc_id,
                    "images": images,
                    "texts": texts,
                    "text_positions": text_positions,
                    "pages": pages,
                }
            )
    except RedisError as exc:
        logger.error("RedisError during get_progress: %s", exc, exc_info=sys.exc_info())
        response = [
            {"doc_id": doc_id, "images": None, "texts": None, "text_positions": None}
            for doc_id in doc_ids
        ]

    return encode_response(response)


@processing_auth
def import_documents(request, _context=None):
    """Command to start the import process on an organization"""
    data = get_http_data(request)
    publisher.publish(START_IMPORT_TOPIC, data=encode_pubsub_data(data))


@processing_auth
def sidekick(request, _context=None):
    """Kick off sidekick processing lambda"""
    data = get_http_data(request)
    publisher.publish(SIDEKICK_PREPROCESS_TOPIC, data=encode_pubsub_data(data))
    return encode_response("Ok")


@pubsub_function(REDIS, RETRY_ERROR_TOPIC)
def retry_errors(_data, _context=None):
    """Retry API requests which failed"""

    logger.info("[RETRY ERRORS] start")

    # set lock expiration time to 15 minutes
    # lambda timout is 15 minutes, so no chance for the lock to expire
    # while the lambda is still running
    try:
        with REDIS.lock(
            redis_fields.error_retry_lock(), timeout=900, blocking_timeout=0
        ):

            logger.info(
                "[RETRY ERRORS] acquired lock, queue size %s",
                REDIS.llen(redis_fields.error_retry_queue()),
            )

            # if we get 3 5xx errors, assume the server is down and stop trying until we
            # get another success
            errors = 3

            request_data = REDIS.rpop(redis_fields.error_retry_queue())
            while request_data is not None:
                request_data = json.loads(request_data)
                logger.info("[RETRY ERRORS] request data: %s", request_data)
                # rate limit
                time.sleep(0.2)
                response = utils.request(
                    REDIS,
                    request_data["method"],
                    request_data["url"],
                    request_data["json"],
                )
                if response.status_code >= 500:
                    errors -= 1
                    logger.info(
                        "[RETRY ERRORS] errors left: %s code: %s",
                        errors,
                        response.status_code,
                    )
                    if errors <= 0:
                        break
                request_data = REDIS.rpop(redis_fields.error_retry_queue())

            logger.info("[RETRY ERRORS] done")

    except LockError:
        logger.info("[RETRY ERRORS] failed to acquire lock")
