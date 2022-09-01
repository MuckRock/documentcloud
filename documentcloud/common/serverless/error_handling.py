"""
A wrapper function to call a cloud function with timeouts, retries, and error
handling baked in.
"""

# Standard Library
import logging
import sys
from concurrent import futures
from functools import wraps

# Third Party
import environ
from pebble import concurrent
from pebble.common import ProcessExpired

# Local
from .. import redis_fields
from ..environment import encode_pubsub_data, get_pubsub_data, publisher
from . import utils

env = environ.Env()

USE_TIMEOUT = env.bool("USE_TIMEOUT", True)
TIMEOUTS = env.list("TIMEOUTS", cast=int)
DEFAULT_TIMEOUTS = TIMEOUTS if USE_TIMEOUT else None
RUN_COUNT = "runcount"


def pubsub_function(
    redis, pubsub_topic, timeouts=DEFAULT_TIMEOUTS, skip_processing_check=False
):
    # pylint: disable=unnecessary-lambda-assignment
    def decorator(func):
        def wrapper(*args, **kwargs):
            def err_handle_func(*args_, **kwargs_):
                # We want to handle arbitrary exceptions from within the concurrent
                # thread so that Sentry has the full traceback
                try:
                    return func(*args_, **kwargs_)
                except Exception as exc:  # pylint: disable=broad-except
                    # Handle any error that comes up during function execution
                    utils.send_error(
                        redis, None if skip_processing_check else doc_id, exc=exc
                    )
                    return f"An error has occurred: {exc}"

            # Get data
            data = get_pubsub_data(args[0])
            doc_id = data.get("doc_id")

            # Return prematurely if there is an error or all processing is complete
            # extra checks are to skip processing check if this is an import
            # function
            if (
                doc_id
                and not skip_processing_check
                and not data.get("import")
                and not data.get("page_modification")
                and not utils.still_processing(redis, doc_id)
            ):
                logging.warning(
                    "Skipping function execution since processing has stopped"
                )
                return "ok"

            if USE_TIMEOUT and timeouts is not None:
                # Handle exceeding maximum number of retries
                run_count = data.get(RUN_COUNT, 0)
                if run_count >= len(timeouts):
                    # Error out
                    utils.send_error(
                        redis,
                        None if skip_processing_check else doc_id,
                        message="Function has timed out (max retries exceeded)",
                    )
                    return "ok"

                # Set up the timeout
                timeout_seconds = timeouts[run_count]
                concurrent_func = concurrent.process(timeout=timeout_seconds)(
                    err_handle_func
                )
                future = concurrent_func(*args, **kwargs)
                func_ = future.result
            else:
                func_ = lambda: err_handle_func(*args, **kwargs)

            try:
                # Run the function as originally intended
                return func_()
            except futures.TimeoutError:
                # Retry the function with increased run count
                logging.warning(
                    "Function timed out: doc_id: %s retrying (run %d)",
                    doc_id,
                    run_count + 2,
                )
                data[RUN_COUNT] = run_count + 1
                publisher.publish(pubsub_topic, data=encode_pubsub_data(data))

        return wraps(func)(wrapper)

    return decorator


def pubsub_function_import(redis, finish_pubsub_topic):
    def decorator(func):
        def wrapper(*args, **kwargs):

            # Get data
            data = get_pubsub_data(args[0])
            doc_id = data.get("doc_id")
            org_id = data.get("org_id")
            slug = data.get("slug")

            # Set up the timeout
            timeout_seconds = 800  # lambda timeout is 900
            concurrent_func = concurrent.process(timeout=timeout_seconds)(func)
            future = concurrent_func(*args, **kwargs)

            try:
                # Run the function as originally intended
                return future.result()
            except (futures.TimeoutError, ProcessExpired, MemoryError):
                # if we timeout or have, skip to finish import
                # sometimes we have odd ProcessExpired exceptions - just skip
                # if the doc is too large and causes a memory error, skip
                redis.hset(redis_fields.import_pagespecs(org_id), doc_id, "")
                publisher.publish(
                    finish_pubsub_topic,
                    encode_pubsub_data(
                        {"org_id": org_id, "doc_id": doc_id, "slug": slug}
                    ),
                )
                return None
            except Exception as exc:  # pylint: disable=broad-except
                # Handle any error that comes up during function execution
                logging.error(exc, exc_info=sys.exc_info())
                return "An error has occurred"

        return wraps(func)(wrapper)

    return decorator
