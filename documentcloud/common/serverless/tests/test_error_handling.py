# Standard Library
import time
import uuid
from functools import wraps
from unittest.mock import call, patch

# Third Party
import fakeredis

# DocumentCloud
from documentcloud.common.environment import (
    encode_pubsub_data,
    get_pubsub_data,
    publisher,
)

# Local
from ...environment.local.pubsub import encode_published_pubsub_data
from ..error_handling import pubsub_function
from ..utils import initialize

server = fakeredis.FakeServer()
redis = fakeredis.FakeStrictRedis(server=server)

initialize(redis, 1)


def communicate_data(*args):  # pylint: disable=unused-argument
    """A simple method to inspect for data communicated in test methods"""


def encode(data):
    """Encodes data in a format expected by pubsub functions invoked directly"""
    return encode_published_pubsub_data(encode_pubsub_data(data))


def with_timeout(timeouts):
    def decorator(func):
        def wrapper(*args, **kwargs):
            topic_name = uuid.uuid4()
            topic = ("test_error_handling", topic_name)
            wrapped_fn = pubsub_function(redis, topic, timeouts)(func)
            publisher.register_internal_callback(topic, wrapped_fn)
            return wrapped_fn(*args, **kwargs)

        return wraps(func)(wrapper)

    return decorator


@with_timeout([1, 2, 4])
def success_on_first_try(data):
    data = get_pubsub_data(data)
    communicate_data("Pending", data)
    communicate_data("Done", data)


@with_timeout([1, 2, 4])
def success_on_third_try(data):
    data = get_pubsub_data(data)
    communicate_data("Pending", data)
    time.sleep(3)
    communicate_data("Done", data)


@with_timeout([1])
def timeout_on_first_try(data):
    data = get_pubsub_data(data)
    communicate_data("Pending", data)
    time.sleep(2)
    communicate_data("Done", data)


@with_timeout([1, 1])
def timeout_on_second_try(data):
    data = get_pubsub_data(data)
    communicate_data("Pending", data)
    time.sleep(2)
    communicate_data("Done", data)


class TestErrorHandling:
    @patch("documentcloud.common.serverless.tests.test_error_handling.communicate_data")
    @patch("documentcloud.common.serverless.utils.send_update")
    @patch("documentcloud.common.serverless.utils.send_error")
    def test_success_on_first_try(
        self, mock_send_error, mock_send_update, mock_communicate_data
    ):
        success_on_first_try(encode({"doc_id": 1}))
        mock_send_error.assert_not_called()
        mock_send_update.assert_not_called()
        assert mock_communicate_data.mock_calls == [
            call("Pending", {"doc_id": 1}),
            call("Done", {"doc_id": 1}),
        ]

    @patch("documentcloud.common.serverless.tests.test_error_handling.communicate_data")
    @patch("documentcloud.common.serverless.utils.send_update")
    @patch("documentcloud.common.serverless.utils.send_error")
    def test_success_on_third_try(
        self, mock_send_error, mock_send_update, mock_communicate_data
    ):
        success_on_third_try(encode({"doc_id": 1}))
        mock_send_error.assert_not_called()
        mock_send_update.assert_not_called()
        assert mock_communicate_data.mock_calls == [
            call("Pending", {"doc_id": 1}),
            call("Pending", {"doc_id": 1, "runcount": 1}),
            call("Pending", {"doc_id": 1, "runcount": 2}),
            call("Done", {"doc_id": 1, "runcount": 2}),
        ]

    @patch("documentcloud.common.serverless.tests.test_error_handling.communicate_data")
    @patch("documentcloud.common.serverless.utils.send_update")
    @patch("documentcloud.common.serverless.utils.send_error")
    def test_timeout_on_first_try(
        self, mock_send_error, mock_send_update, mock_communicate_data
    ):
        timeout_on_first_try(encode({"doc_id": 1}))
        mock_send_error.assert_called_once()
        mock_send_update.assert_not_called()
        mock_communicate_data.assert_called_once_with("Pending", {"doc_id": 1})

    @patch("documentcloud.common.serverless.tests.test_error_handling.communicate_data")
    @patch("documentcloud.common.serverless.utils.send_update")
    @patch("documentcloud.common.serverless.utils.send_error")
    def test_timeout_on_second_try(
        self, mock_send_error, mock_send_update, mock_communicate_data
    ):
        timeout_on_second_try(encode({"doc_id": 1}))
        mock_send_error.assert_called_once()
        mock_send_update.assert_not_called()
        assert mock_communicate_data.mock_calls == [
            call("Pending", {"doc_id": 1}),
            call("Pending", {"doc_id": 1, "runcount": 1}),
        ]
