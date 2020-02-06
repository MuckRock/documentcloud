# Django
from django.conf import settings

# Standard Library
import ctypes
import os.path
import time
import uuid
from functools import wraps
from unittest.mock import call, patch

# Third Party
from sharedmock.mock import SharedMock

# DocumentCloud
from documentcloud.common import redis_fields
from documentcloud.common.environment import (
    encode_pubsub_data,
    get_pubsub_data,
    publisher,
)
from documentcloud.common.environment.local.pubsub import encode_published_pubsub_data
from documentcloud.common.environment.local.storage import storage
from documentcloud.common.serverless.error_handling import pubsub_function
from documentcloud.documents.processing.info_and_image.pdfium import (
    StorageHandler,
    Workspace,
)

# Since redis is used in the SharedMock calls, it needs to be pickle-able
# in order to be sent across the process boundary.  FakeRedis and Mock's both
# have issues with being pickled.  All we use this variable for in these tests
# is to check if the process is running, which can be succesfully simulated using
# the following dictionary, which is very pickle-able.
redis = {redis_fields.is_running(1): b"1"}


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


class SlowStorageHandler(StorageHandler):
    """Simulate a slow CFUNCTYPE callback in order to test time outs within
    C code
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.sleep = True

        @ctypes.CFUNCTYPE(
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_ulong,
        )
        def get_block(_param, position, p_buf, size):
            # only sleep once so if the timeout fails the test doesn't run on
            if self.sleep:
                time.sleep(2)
                self.sleep = False
            return size

        self.get_block = get_block


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


@with_timeout([1])
def timeout_cfunctype(data):
    pdf = os.path.join(
        settings.ROOT_DIR,
        "documentcloud",
        "documents",
        "processing",
        "tests",
        "pdfs",
        "doc_3.pdf",
    )
    with Workspace() as workspace, SlowStorageHandler(
        storage, pdf
    ) as pdf_file, workspace.load_document_custom(pdf_file) as doc:
        return doc.load_page(1)


class TestErrorHandling:
    @patch(
        "documentcloud.common.serverless.tests.test_error_handling.communicate_data",
        new_callable=SharedMock,
    )
    @patch("documentcloud.common.serverless.utils.send_update", new_callable=SharedMock)
    @patch("documentcloud.common.serverless.utils.send_error", new_callable=SharedMock)
    def test_success_on_first_try(
        self, mock_send_error, mock_send_update, mock_communicate_data
    ):
        success_on_first_try(encode({"doc_id": 1}))
        assert mock_send_error.call_count == 0
        assert mock_send_update.call_count == 0
        assert mock_communicate_data.mock_calls == [
            call("Pending", {"doc_id": 1}),
            call("Done", {"doc_id": 1}),
        ]

    @patch(
        "documentcloud.common.serverless.tests.test_error_handling.communicate_data",
        new_callable=SharedMock,
    )
    @patch("documentcloud.common.serverless.utils.send_update", new_callable=SharedMock)
    @patch("documentcloud.common.serverless.utils.send_error", new_callable=SharedMock)
    def test_success_on_third_try(
        self, mock_send_error, mock_send_update, mock_communicate_data
    ):
        success_on_third_try(encode({"doc_id": 1}))
        assert mock_send_error.call_count == 0
        assert mock_send_update.call_count == 0
        assert mock_communicate_data.mock_calls == [
            call("Pending", {"doc_id": 1}),
            call("Pending", {"doc_id": 1, "runcount": 1}),
            call("Pending", {"doc_id": 1, "runcount": 2}),
            call("Done", {"doc_id": 1, "runcount": 2}),
        ]

    @patch(
        "documentcloud.common.serverless.tests.test_error_handling.communicate_data",
        new_callable=SharedMock,
    )
    @patch("documentcloud.common.serverless.utils.send_update", new_callable=SharedMock)
    @patch("documentcloud.common.serverless.utils.send_error", new_callable=SharedMock)
    def test_timeout_on_first_try(
        self, mock_send_error, mock_send_update, mock_communicate_data
    ):
        timeout_on_first_try(encode({"doc_id": 1}))
        assert mock_send_error.call_count == 1
        assert mock_send_update.call_count == 0
        assert mock_communicate_data.mock_calls == [call("Pending", {"doc_id": 1})]

    @patch(
        "documentcloud.common.serverless.tests.test_error_handling.communicate_data",
        new_callable=SharedMock,
    )
    @patch("documentcloud.common.serverless.utils.send_update", new_callable=SharedMock)
    @patch("documentcloud.common.serverless.utils.send_error", new_callable=SharedMock)
    def test_timeout_on_second_try(
        self, mock_send_error, mock_send_update, mock_communicate_data
    ):
        timeout_on_second_try(encode({"doc_id": 1}))
        assert mock_send_error.call_count == 1
        assert mock_send_update.call_count == 0
        assert mock_communicate_data.mock_calls == [
            call("Pending", {"doc_id": 1}),
            call("Pending", {"doc_id": 1, "runcount": 1}),
        ]

    @patch("documentcloud.common.serverless.utils.send_error")
    def test_timeout_cfunctype(self, mock_send_error):
        timeout_cfunctype(encode({"doc_id": 1}))
        mock_send_error.assert_called_with(
            redis, 1, "Function has timed out (max retries exceeded)"
        )
