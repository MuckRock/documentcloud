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

if env.str("ENVIRONMENT") == "local":
    # Load from Django imports if in a local environment
    from documentcloud.documents.processing.ocr.tess import Tesseract
    from documentcloud.documents.processing.ocr.environment import (
        storage,
        publisher,
        get_pubsub_data,
    )
else:
    # Otherwise, load directly as a package to be compatible with cloud functions
    from tess import Tesseract
    from environment import storage, publisher, get_pubsub_data

redis_url = furl.furl(env.str("REDIS_PROCESSING_URL"))
redis = redis.Redis(host=redis_url.host, port=redis_url.port, db=0)
bucket = env.str("BUCKET", default="")

ocr_topic = publisher.topic_path(
    "documentcloud", env.str("OCR_TOPIC", default="ocr-queue")
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
    paths = data["paths"]

    result = {}

    if env.bool("CLOUD", default=False):
        # Perform speed thresholding to prevent running OCR on a slow CPU
        speed = profile_cpu(CPU_DIFFICULTY)
        if speed > SPEED_THRESHOLD:
            # Resubmit to queue
            publisher.publish(
                ocr_topic, data=json.dumps({"paths": paths}).encode("utf8")
            )
            logging.warning("Too slow (speed: %f)", speed)
            return "Too slow, retrying"

        result["speed"] = speed

    # Keep track of how long OCR takes (useful for profiling)
    elapsed_times = []

    if not paths:
        logging.warning("No paths")
        return "Ok"

    path = os.path.join(bucket, paths[0])
    doc_id = get_id(path)
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

    texts_remaining = redis.hincrby(doc_id, "text", -1)
    if texts_remaining == 0:
        requests.patch(
            urljoin(env.str("API_CALLBACK"), f"documents/{get_id(path)}/"),
            json={"status": "success"},
            headers={
                "Authorization": f"processing-token {env.str('PROCESSING_TOKEN')}"
            },
        )
    else:
        next_paths = paths[1:]
        if next_paths:
            # Launch next iteration
            publisher.publish(
                ocr_topic, data=json.dumps({"paths": next_paths}).encode("utf8")
            )

    result["path"] = path
    result["elapsed"] = elapsed_times
    result["status"] = "Ok"
    result["overall_elapsed"] = time.time() - overall_start
    result["speed_after"] = profile_cpu()
    return json.dumps(result)
