"""
A wrapper function to call a cloud function with timeouts, retries, and error
handling baked in.
"""

# Standard Library
from functools import wraps
import errno
import logging
import os
import signal

# Third party
import environ

# Common
from . import tasks
from .. import redis_fields
from ..environment import get_pubsub_data, encode_pubsub_data, publisher


env = environ.Env()

TIMEOUTS = env.list("TIMEOUTS", cast=int)
RUN_COUNT = "runcount"


class TimeoutError(Exception):
    pass


def pubsub_function(redis, pubsub_topic, timeouts=TIMEOUTS):
    def decorator(func):
        def _handle_timeout(signum, frame):
            raise TimeoutError()

        def wrapper(*args, **kwargs):

            # Get data
            data = get_pubsub_data(args[0])
            doc_id = data["doc_id"]

            # Return prematurely if there is an error or all processing is complete
            if not tasks.still_processing(redis, doc_id):
                logging.warning(
                    "Skipping function execution since processing has stopped"
                )
                return

            # Handle exceeding maximum number of retries
            run_count = data.get(RUN_COUNT, 0)
            if run_count >= len(timeouts):
                # Error out
                tasks.send_error(
                    redis, doc_id, "Function has timed out (max retries exceeded)"
                )
                return

            # Set up the timeout
            timeout_seconds = timeouts[run_count]
            signal.signal(signal.SIGALRM, _handle_timeout)
            signal.alarm(timeout_seconds)

            try:
                # Run the function as originally intended
                return func(*args, **kwargs)
            except TimeoutError:
                # Retry the function with increased run count
                logging.warning(f"Function timed out: retrying (run {run_count + 2})")
                data[RUN_COUNT] = run_count + 1
                publisher.publish(pubsub_topic, data=encode_pubsub_data(data))
            except Exception as e:
                # Handle any error that comes up during function execution
                error_message = str(e)
                tasks.send_error(redis, doc_id, error_message, True)
                return f"An error has occurred: {error_message}"
            finally:
                # Clear out the timeout alarm
                signal.alarm(0)

        return wraps(func)(wrapper)

    return decorator
