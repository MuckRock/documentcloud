"""
A wrapper function to call a cloud function with timeouts, retries, and error
handling baked in.
"""

# Standard Library
import logging
import signal
from concurrent.futures import TimeoutError
from datetime import datetime
from functools import wraps

# Third Party
import environ
from pebble import concurrent

# Local
from ..environment import encode_pubsub_data, get_pubsub_data, publisher
from . import utils

env = environ.Env()

USE_TIMEOUT = env.bool("USE_TIMEOUT", True)
TIMEOUTS = env.list("TIMEOUTS", cast=int)
DEFAULT_TIMEOUTS = TIMEOUTS if USE_TIMEOUT else None
RUN_COUNT = "runcount"


def pubsub_function(redis, pubsub_topic, timeouts=DEFAULT_TIMEOUTS):
    def decorator(func):
        def wrapper(*args, **kwargs):

            # Get data
            data = get_pubsub_data(args[0])
            doc_id = data["doc_id"]

            # Return prematurely if there is an error or all processing is complete
            if not utils.still_processing(redis, doc_id):
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
                        redis, doc_id, "Function has timed out (max retries exceeded)"
                    )
                    return "ok"

                # Set up the timeout
                timeout_seconds = timeouts[run_count]
                concurrent_func = concurrent.process(timeout=timeout_seconds)(func)
                future = concurrent_func(*args, **kwargs)
                func_ = future.result
            else:
                func_ = lambda: func(*args, **kwargs)

            try:
                # Run the function as originally intended
                return func_()
            except TimeoutError:
                # Retry the function with increased run count
                logging.warning("Function timed out: retrying (run %d)", run_count + 2)
                data[RUN_COUNT] = run_count + 1
                publisher.publish(pubsub_topic, data=encode_pubsub_data(data))
            except Exception as exc:  # pylint: disable=broad-except
                # Handle any error that comes up during function execution
                error_message = str(exc)
                utils.send_error(redis, doc_id, error_message, True)
                return f"An error has occurred: {error_message}"

        return wraps(func)(wrapper)

    return decorator
