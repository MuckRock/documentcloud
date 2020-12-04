# Standard Library
import logging
import sys
from itertools import zip_longest

# Third Party
import environ
from redis.exceptions import RedisError

env = environ.Env()
logger = logging.getLogger(__name__)

# Imports based on execution context
if env.str("ENVIRONMENT").startswith("local"):
    from documentcloud.common import redis_fields
    from documentcloud.common.environment import (
        get_http_data,
        publisher,
        encode_pubsub_data,
        encode_response,
        processing_auth,
    )
    from documentcloud.common.serverless import utils
else:
    from common import redis_fields
    from common.environment import (
        get_http_data,
        publisher,
        encode_pubsub_data,
        encode_response,
        processing_auth,
    )
    from common.serverless import utils

    # only initialize sentry on serverless
    # pylint: disable=import-error
    import sentry_sdk
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    # pylint: enable=import-error

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
START_IMPORT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("START_IMPORT_TOPIC", default="start-import")
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

    if not doc_ids:
        doc_ids = [doc_id]

    response = []

    try:
        redis_progress_fields = []
        for doc_id in doc_ids:
            redis_progress_fields.append(redis_fields.images_remaining(doc_id))
            redis_progress_fields.append(redis_fields.texts_remaining(doc_id))
        data = grouper(
            (int(i) if i is not None else i for i in REDIS.mget(redis_progress_fields)),
            2,
        )
        for doc_id, (images, texts) in zip(doc_ids, data):
            response.append({"doc_id": doc_id, "images": images, "texts": texts})
    except RedisError as exc:
        logger.error("RedisError during get_progress: %s", exc, exc_info=sys.exc_info())
        response = [
            {"doc_id": doc_id, "images": None, "texts": None} for doc_id in doc_ids
        ]

    return encode_response(response)


@processing_auth
def import_documents(request, _context=None):
    """Command to start the import process on an organization"""
    data = get_http_data(request)
    publisher.publish(START_IMPORT_TOPIC, data=encode_pubsub_data(data))
