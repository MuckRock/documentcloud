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

# Local
from .environment import get_pubsub_data, publisher, redis_fields, storage
from .tess import Tesseract

env = environ.Env()


REDIS_URL = furl.furl(env.str("REDIS_PROCESSING_URL"))
REDIS_PASSWORD = env.str("REDIS_PROCESSING_PASSWORD")
REDIS = redis.Redis(
    host=REDIS_URL.host, port=REDIS_URL.port, password=REDIS_PASSWORD, db=0
)

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


def get_id(img_path):
    """Returns the document ID associated with the image path."""
    return img_path.split("/")[-3]


def ocr_page(path):
    """Internal method to run OCR on a single page.

    Returns:
        The page text.
    """
    # Capture the image as raw pixel data
    with storage.open(path, "rb") as image_file:
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
                data=json.dumps({"paths_and_numbers": paths_and_numbers}).encode(
                    "utf8"
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

    path = paths_and_numbers[0][1]
    page_number = paths_and_numbers[0][0]
    doc_id = get_id(path)

    texts_remaining_field = redis_fields.texts_remaining(doc_id)
    text_bits_field = redis_fields.text_bits(doc_id)

    # Only OCR if the page has yet to be OCRd
    if REDIS.getbit(text_bits_field, page_number) == 0:
        ext = "." + path.split(".")[-1]
        assert len(ext) > 1, "Needs an extension"
        # Derive a simple filename for OCRd text
        new_path = ".".join(path.split(".")[:-1])
        assert new_path.endswith(LARGE_IMAGE_SUFFIX)
        new_path = new_path[: -len(LARGE_IMAGE_SUFFIX)] + TXT_EXTENSION

        # Benchmark OCR speed
        start_time = time.time()
        text = ocr_page(path)

        elapsed_time = time.time() - start_time
        elapsed_times.append(elapsed_time)

        # Write the output text
        with storage.open(new_path, "wb") as text_file:
            text_file.write(text.encode("utf8"))

        # Decrement texts remaining and set the bit for the page off atomically
        pipeline = REDIS.pipeline()
        pipeline.decr(texts_remaining_field)
        pipeline.setbit(text_bits_field, page_number, 1)
        texts_remaining = pipeline.execute()[0]

        # Check if finished
        if texts_remaining == 0:
            requests.patch(
                urljoin(env.str("API_CALLBACK"), f"documents/{get_id(path)}/"),
                json={"status": "success"},
                headers={
                    "Authorization": f"processing-token {env.str('PROCESSING_TOKEN')}"
                },
            )
            return "Ok"

    next_paths_and_numbers = paths_and_numbers[1:]
    if next_paths_and_numbers:
        # Launch next iteration
        publisher.publish(
            OCR_TOPIC,
            data=json.dumps({"paths_and_numbers": next_paths_and_numbers}).encode(
                "utf8"
            ),
        )

    result["path"] = path
    result["elapsed"] = elapsed_times
    result["status"] = "Ok"
    result["overall_elapsed"] = time.time() - overall_start
    result["speed_after"] = profile_cpu()
    return json.dumps(result)
