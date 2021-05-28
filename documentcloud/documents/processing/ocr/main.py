# Standard Library
import json
import logging
import os
import tempfile
import time

# Third Party
import environ
from cpuprofile import profile_cpu
from PIL import Image

env = environ.Env()
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Imports based on execution context
if env.str("ENVIRONMENT").startswith("local"):
    from documentcloud.common import path, access_choices
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
    from common import path, access_choices
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
    # pylint: disable=import-error
    import sentry_sdk
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    # pylint: enable=import-error

    sentry_sdk.init(
        dsn=env("SENTRY_DSN"), integrations=[AwsLambdaIntegration(), RedisIntegration()]
    )


REDIS = utils.get_redis()

OCR_TOPIC = publisher.topic_path(
    "documentcloud", env.str("OCR_TOPIC", default="ocr-eng-extraction-dev")
)
ASSEMBLE_TEXT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("ASSEMBLE_TEXT_TOPIC", default="assemble-text")
)
OCR_VERSION = env.str("OCR_VERSION", default="tess4")

# Ensures running on roughly 2Ghz+ machine
PROFILE_CPU = env.bool("PROFILE_CPU", default=False)
SPEED_THRESHOLD = env.float("SPEED_THRESHOLD", default=0.0039)
CPU_DIFFICULTY = env.int("CPU_DIFFICULTY", default=20)

# Width of images to use with OCR (aspect ratio is preserved)
DESIRED_WIDTH = env.int("OCR_WIDTH", default=700)

LARGE_IMAGE_SUFFIX = "-large"
TXT_EXTENSION = ".txt"

TESS_PDF_PREFIX = "ocr"


def write_text_file(text_path, text, access):
    """Helper method to write a text file."""
    storage.simple_upload(text_path, text.encode("utf8"), access=access)


def ocr_page(page_path, upload_text_path, access, ocr_code="eng"):
    """Internal method to run OCR on a single page.

    Returns:
        The page text.
    """
    # Initialize temporary files
    tmp_files = {
        "img": tempfile.mkstemp(suffix=".png")[1],
        "pdf": tempfile.mkstemp()[1],
        "text": tempfile.mkstemp()[1],
    }

    # Capture the page image as a temporary PNG file
    with storage.open(page_path, "rb") as image_file:
        img = Image.open(image_file).convert("RGB")
        # Resize only if image is too big (OCR computation is slow with large images)
        if img.width > DESIRED_WIDTH:
            resize = DESIRED_WIDTH / img.width
            img = img.resize(
                (DESIRED_WIDTH, round(img.height * resize)), Image.ANTIALIAS
            )
    img.save(tmp_files["img"], "png")

    # Use Tesseract OCR to render a text-only PDF and txt file
    tess = Tesseract(ocr_code)
    text = ""
    pdf_contents = b""
    try:
        tess.create_renderer(tmp_files["pdf"], tmp_files["text"])
        tess.render(tmp_files["img"])
        tess.destroy_renderer()

        # Get txt and text-only pdf file contents
        with open(tmp_files["pdf"] + ".pdf", "rb") as pdf_file:
            pdf_contents = pdf_file.read()
        with storage.open(upload_text_path, "w", access=access) as new_text_file:
            with open(tmp_files["text"] + ".txt", "r") as text_file:
                # Store text locally to return (gets used by Redis later)
                text = text_file.read()
                # Also upload text file to s3
                new_text_file.write(text)
    finally:
        os.remove(tmp_files["pdf"])
        os.remove(tmp_files["text"])
        os.remove(tmp_files["img"])

    return text, pdf_contents


@pubsub_function(REDIS, OCR_TOPIC)
def run_tesseract(data, _context=None):
    """Runs OCR on the images passed in, storing the extracted text.
    """
    # pylint: disable=too-many-locals
    overall_start = time.time()

    data = get_pubsub_data(data)
    doc_id = data["doc_id"]
    slug = data["slug"]
    access = data.get("access", access_choices.PRIVATE)
    ocr_code = data.get("ocr_code", "eng")
    paths_and_numbers = data["paths_and_numbers"]
    partial = data["partial"]  # Whether it is a partial update (e.g. redaction) or not
    force_ocr = data["force_ocr"]
    if force_ocr:
        ocr_version = f"{OCR_VERSION}_force"
    else:
        ocr_version = OCR_VERSION

    logger.info(
        "[RUN TESSERACT] doc_id %s ocr_code %s ocr_version %s page_numbers %s",
        doc_id,
        ocr_code,
        ocr_version,
        ",".join([str(number[0]) for number in paths_and_numbers]),
    )

    result = {}

    if PROFILE_CPU:
        # Perform speed thresholding to prevent running OCR on a slow CPU
        speed = profile_cpu(CPU_DIFFICULTY)
        if speed > SPEED_THRESHOLD:
            # Resubmit to queue
            publisher.publish(
                OCR_TOPIC,
                data=encode_pubsub_data(
                    {
                        "paths_and_numbers": paths_and_numbers,
                        "doc_id": doc_id,
                        "slug": slug,
                        "access": access,
                        "ocr_code": ocr_code,
                        "partial": partial,
                        "force_ocr": force_ocr,
                    }
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

    # Loop through all paths and numbers
    for page_number, image_path in paths_and_numbers:

        # Only OCR if the page has yet to be OCRd
        if not utils.page_ocrd(REDIS, doc_id, page_number):
            text_path = path.page_text_path(doc_id, slug, page_number)

            # Benchmark OCR speed
            start_time = time.time()
            text, pdf_contents = ocr_page(image_path, text_path, access, ocr_code)

            elapsed_time = time.time() - start_time
            elapsed_times.append(elapsed_time)

            # Write the output text and pdf to Redis
            utils.write_page_text(
                REDIS, doc_id, page_number, text, ocr_version, ocr_code
            )
            utils.write_page_text_pdf(REDIS, doc_id, page_number, pdf_contents)

            # Decrement the texts remaining, sending complete if done.
            texts_finished = utils.register_page_ocrd(REDIS, doc_id, page_number)
            if texts_finished:
                publisher.publish(
                    ASSEMBLE_TEXT_TOPIC,
                    encode_pubsub_data(
                        {
                            "doc_id": doc_id,
                            "slug": slug,
                            "access": access,
                            "ocr_code": ocr_code,
                            "partial": partial,
                        }
                    ),
                )
                return "Ok"

    result["doc_id"] = doc_id
    result["elapsed"] = elapsed_times
    result["status"] = "Ok"
    result["overall_elapsed"] = time.time() - overall_start
    if PROFILE_CPU:
        result["speed_after"] = profile_cpu()
    return json.dumps(result)
