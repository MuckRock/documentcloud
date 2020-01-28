# Standard Library
import json
import logging
import time

# Third Party
import environ
import numpy as np
from cpuprofile import profile_cpu
from PIL import Image

env = environ.Env()

# Imports based on execution context
if env.str("ENVIRONMENT").startswith("local"):
    from documentcloud.common import path
    from documentcloud.common.environment import (
        get_pubsub_data,
        encode_pubsub_data,
        publisher,
        storage,
    )
    from documentcloud.common.serverless import utils
    from documentcloud.common.serverless.error_handling import pubsub_function
    from documentcloud.documents.processing.ocr.tess import Tesseract
else:
    from common import path
    from common.environment import (
        get_pubsub_data,
        encode_pubsub_data,
        publisher,
        storage,
    )
    from common.serverless import utils
    from common.serverless.error_handling import pubsub_function
    from tess import Tesseract

    # only initialize sentry on serverless
    import sentry_sdk
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

    sentry_sdk.init(dsn=env("SENTRY_DSN"), integrations=[AwsLambdaIntegration()])


REDIS = utils.get_redis()

OCR_TOPIC = publisher.topic_path(
    "documentcloud", env.str("OCR_TOPIC", default="ocr-extraction")
)

# Ensures running on roughly 2Ghz+ machine
SPEED_THRESHOLD = env.float("SPEED_THRESHOLD", default=0.0039)
CPU_DIFFICULTY = env.int("CPU_DIFFICULTY", default=20)

# Width of images to use with OCR (aspect ratio is preserved)
DESIRED_WIDTH = env.int("OCR_WIDTH", default=700)

LARGE_IMAGE_SUFFIX = "-large"
TXT_EXTENSION = ".txt"


def write_text_file(text_path, text):
    """Helper method to write a text file."""
    with storage.open(text_path, "wb") as text_file:
        text_file.write(text.encode("utf8"))


def ocr_page(page_path):
    """Internal method to run OCR on a single page.

    Returns:
        The page text.
    """
    # Capture the image as raw pixel data
    with storage.open(page_path, "rb") as image_file:
        img = Image.open(image_file).convert("RGB")
    # Resize only if image is too big (OCR computation is slow with large images)
    if img.width > DESIRED_WIDTH:
        resize = DESIRED_WIDTH / img.width
        img = img.resize((DESIRED_WIDTH, round(img.height * resize)), Image.ANTIALIAS)

    img_data = np.array(img.convert("RGB"))
    height, width, depth = img_data.shape  # pylint: disable=unpacking-non-sequence

    # Run Tesseract OCR on the image
    tess = Tesseract()
    tess.set_image(img_data.ctypes, width, height, depth)
    text = tess.get_text()
    return text


@pubsub_function(REDIS, OCR_TOPIC)
def run_tesseract(data, _context=None):
    """Runs OCR on the images passed in, storing the extracted text.
    """
    overall_start = time.time()

    data = get_pubsub_data(data)
    doc_id = data["doc_id"]
    paths_and_numbers = data["paths_and_numbers"]

    result = {}

    if env.bool("CLOUD", default=False):
        # Perform speed thresholding to prevent running OCR on a slow CPU
        speed = profile_cpu(CPU_DIFFICULTY)
        if speed > SPEED_THRESHOLD:
            # Resubmit to queue
            publisher.publish(
                OCR_TOPIC,
                data=encode_pubsub_data(
                    {"paths_and_numbers": paths_and_numbers, "doc_id": doc_id}
                ),
            )
            logging.warning("Too slow (speed: %f)", speed)
            return "Too slow, retrying"

        result["speed"] = speed

    # Keep track of how long OCR takes (useful for profiling)
    elapsed_times = []

    if not paths_and_numbers:
        logging.warning("No paths/numbers")
        return "Ok"

    doc_id, slug, page_number, image_path = paths_and_numbers[0]

    # Only OCR if the page has yet to be OCRd
    if not utils.page_ocrd(REDIS, doc_id, page_number):
        text_path = path.page_text_path(doc_id, slug, page_number)

        # Benchmark OCR speed
        start_time = time.time()
        text = ocr_page(image_path)

        elapsed_time = time.time() - start_time
        elapsed_times.append(elapsed_time)

        # Write the output text
        write_text_file(text_path, text)

        # Decrement the texts remaining, sending complete if done.
        texts_finished = utils.register_page_ocrd(REDIS, doc_id, page_number)
        if texts_finished:
            utils.send_complete(REDIS, doc_id)
            return "Ok"

    next_paths_and_numbers = paths_and_numbers[1:]
    if next_paths_and_numbers:
        # Launch next iteration
        publisher.publish(
            OCR_TOPIC,
            data=encode_pubsub_data(
                {"paths_and_numbers": next_paths_and_numbers, "doc_id": doc_id}
            ),
        )

    result["doc_id"] = doc_id
    result["elapsed"] = elapsed_times
    result["status"] = "Ok"
    result["overall_elapsed"] = time.time() - overall_start
    result["speed_after"] = profile_cpu()
    return json.dumps(result)
