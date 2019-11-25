# Standard Library
import json
import logging
import os
import time
from urllib.parse import urljoin

# Third Party
import environ
import furl
import numpy as np
import redis
import requests
from cpuprofile import profile_cpu
from PIL import Image


env = environ.Env()

# Imports based on execution context
# In serverless functions, imports cannot be relative
if env.str("ENVIRONMENT").startswith("local"):
    from .common import path, redis_fields
    from .common.environment import (
        get_pubsub_data,
        encode_pubsub_data,
        publisher,
        storage,
    )
    from .common.serverless import error_handling, tasks
    from .common.serverless.error_handling import pubsub_function
    from .tess import Tesseract
else:
    from common import path, redis_fields
    from common.environment import (
        get_pubsub_data,
        encode_pubsub_data,
        publisher,
        storage,
    )
    from common.serverless import error_handling, tasks
    from common.serverless.error_handling import pubsub_function
    from tess import Tesseract


REDIS = tasks.get_redis()

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
    height, width, depth = img_data.shape

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
    paths_and_numbers = data["paths_and_numbers"]

    result = {}

    if env.bool("CLOUD", default=False):
        # Perform speed thresholding to prevent running OCR on a slow CPU
        speed = profile_cpu(CPU_DIFFICULTY)
        if speed > SPEED_THRESHOLD:
            # Resubmit to queue
            publisher.publish(
                OCR_TOPIC,
                data=encode_pubsub_data({"paths_and_numbers": paths_and_numbers}),
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

    texts_remaining_field = redis_fields.texts_remaining(doc_id)
    text_bits_field = redis_fields.text_bits(doc_id)

    # Only OCR if the page has yet to be OCRd
    if REDIS.getbit(text_bits_field, page_number) == 0:
        text_path = path.page_text_path(doc_id, slug, page_number)

        # Benchmark OCR speed
        start_time = time.time()
        text = ocr_page(image_path)

        elapsed_time = time.time() - start_time
        elapsed_times.append(elapsed_time)

        # Write the output text
        with storage.open(text_path, "wb") as text_file:
            text_file.write(text.encode("utf8"))

        # Decrement texts remaining and set the bit for the page off atomically
        pipeline = REDIS.pipeline()
        pipeline.decr(texts_remaining_field)
        pipeline.setbit(text_bits_field, page_number, 1)
        texts_remaining = pipeline.execute()[0]

        # Check if finished
        if texts_remaining == 0:
            tasks.send_complete(REDIS, doc_id)
            return "Ok"

    next_paths_and_numbers = paths_and_numbers[1:]
    if next_paths_and_numbers:
        # Launch next iteration
        publisher.publish(
            OCR_TOPIC,
            data=encode_pubsub_data({"paths_and_numbers": next_paths_and_numbers}),
        )

    result["doc_id"] = doc_id
    result["elapsed"] = elapsed_times
    result["status"] = "Ok"
    result["overall_elapsed"] = time.time() - overall_start
    result["speed_after"] = profile_cpu()
    return json.dumps(result)
