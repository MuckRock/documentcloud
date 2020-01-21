# Third Party
import environ
import logging
from redis.exceptions import RedisError
import sys

env = environ.Env()
logger = logging.getLogger(__name__)

# Imports based on execution context
if env.str("ENVIRONMENT").startswith("local"):
    from documentcloud.common import redis_fields
    from documentcloud.common.environment import (
        get_http_data,
        publisher,
        encode_pubsub_data,
        processing_auth,
    )
    from documentcloud.common.serverless import utils
else:
    from common import redis_fields
    from common.environment import (
        get_http_data,
        publisher,
        encode_pubsub_data,
        processing_auth,
    )
    from common.serverless import utils

    # only initialize sentry on serverless
    import sentry_sdk
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

    sentry_sdk.init(dsn=env("SENTRY_DSN"), integrations=[AwsLambdaIntegration()])

REDIS = utils.get_redis()

# Topic names for the messaging queue
PDF_PROCESS_TOPIC = publisher.topic_path(
    "documentcloud", env.str("PDF_PROCESS_TOPIC", default="pdf-process")
)
REDACT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("REDACT_TOPIC", default="redact-doc")
)


@processing_auth
def process_doc(request, _context=None):
    """Central command to run processing on a doc"""
    data = get_http_data(request)
    doc_id = data["doc_id"]
    job_type = data["method"]

    # Initialize the processing environment
    utils.initialize(REDIS, doc_id)

    # Launch PDF processing via pubsub
    if job_type == "process_pdf":
        publisher.publish(PDF_PROCESS_TOPIC, data=encode_pubsub_data(data))
    elif job_type == "redact_doc":
        publisher.publish(REDACT_TOPIC, data=encode_pubsub_data(data))
    elif job_type == "cancel_doc_processing":
        utils.clean_up(REDIS, doc_id)
    else:
        logger.error(
            "Invalid doc processing type: %s", job_type, exc_info=sys.exc_info()
        )
        return "Error"

    return "Ok"


@processing_auth
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
