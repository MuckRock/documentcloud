"""
Helper functions to perform common serverless operations.
"""

# Standard Library
import json
from urllib.parse import urljoin

# Third Party
import environ
import furl
import redis
import requests


env = environ.Env()

# Imports based on execution context
# In serverless functions, imports cannot be relative
if env.str("ENVIRONMENT").startswith("local"):
    from .. import redis_fields
else:
    from common import redis_fields


# Common environment variables
API_CALLBACK = env.str("API_CALLBACK")
PROCESSING_TOKEN = env.str("PROCESSING_TOKEN")
REDIS_URL = furl.furl(env.str("REDIS_PROCESSING_URL"))
REDIS_PASSWORD = env.str("REDIS_PROCESSING_PASSWORD")


def get_redis():
    """Opens a connection to Redis and returns it"""
    return redis.Redis(
        host=REDIS_URL.host, port=REDIS_URL.port, password=REDIS_PASSWORD, db=0
    )


def send_update(doc_id, json):
    """Sends an update to the API server specified as JSON"""
    requests.patch(
        urljoin(API_CALLBACK, f"documents/{doc_id}/"),
        json=json,
        headers={"Authorization": f"processing-token {PROCESSING_TOKEN}"},
    )


def send_complete(redis, doc_id):
    """Sends an update to the API server that processing is complete"""
    send_update(doc_id, {"status": "success"})
    # Clean out redis
    clean_up(redis, doc_id)


def send_error(redis, doc_id, message):
    """Sends an error to the API server specified as a string message"""
    # Set the error state in Redis
    redis.set(redis_fields.error(doc_id), message)
    # Send the error to the server
    requests.patch(
        urljoin(API_CALLBACK, f"documents/{doc_id}/errors"),
        json={"message": message},
        headers={"Authorization": f"processing-token {PROCESSING_TOKEN}"},
    )
    clean_up(redis, doc_id)


def initialize(redis, doc_id):
    """Sets up Redis for processing"""
    redis.set(redis_fields.is_running(doc_id), True)


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
        )

        # Remove any existing dimensions that may be lingering
        existing_dimensions = pipeline.get(dimensions_field)
        if existing_dimensions is not None:
            for dimension in existing_dimensions:
                pipeline.delete(redis_fields.page_dimension(doc_id, dimension))
        pipeline.delete(dimensions_field)

    redis.transaction(remove_all, dimensions_field)
