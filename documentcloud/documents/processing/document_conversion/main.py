# Standard Library
import locale
import logging
import os
import shlex
import shutil
import tarfile
import tempfile
from pathlib import Path

# Third Party
import environ

locale.setlocale(locale.LC_ALL, "C")

env = environ.Env()
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Imports based on execution context
if env.str("ENVIRONMENT").startswith("local"):
    # DocumentCloud
    from documentcloud.common import path
    from documentcloud.common.environment import (
        encode_pubsub_data,
        get_pubsub_data,
        publisher,
        storage,
    )
    from documentcloud.common.extensions import EXTENSIONS
    from documentcloud.common.serverless import utils
    from documentcloud.common.serverless.error_handling import pubsub_function
else:
    # Third Party
    # only initialize sentry on serverless
    # pylint: disable=import-error
    import sentry_sdk
    from common import path
    from common.environment import (
        encode_pubsub_data,
        get_pubsub_data,
        publisher,
        storage,
    )
    from common.extensions import EXTENSIONS
    from common.serverless import utils
    from common.serverless.error_handling import pubsub_function
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    # pylint: enable=import-error

    sentry_sdk.init(
        dsn=env("SENTRY_DSN"), integrations=[AwsLambdaIntegration(), RedisIntegration()]
    )

DOCUMENT_SIZE_LIMIT = env.int("DOCUMENT_SIZE_LIMIT", 26 * 1024 * 1024)
SUPPORTED_DOCUMENT_EXTENSIONS = env.list("DOCUMENT_TYPES", default=EXTENSIONS)

REDIS = utils.get_redis()

DOCUMENT_CONVERT_TOPIC = publisher.topic_path(
    "documentcloud", env.str("DOCUMENT_CONVERT_TOPIC", default="document-convert")
)
PDF_PROCESS_TOPIC = publisher.topic_path(
    "documentcloud", env.str("PDF_PROCESS_TOPIC", default="pdf-process")
)


TMP_DIR = "/tmp/"
script_dir = os.path.dirname(os.path.realpath(__file__))

# Where the raw LibreOffice zipped archive is stored
LIBRE_OFFICE_ARCHIVE = os.path.join(script_dir, "libreoffice/lo.tar.gz")

# Where the LibreOffice should be uncompressed
LIBRE_OFFICE_PATH = "/tmp/libreoffice"

# The path of the uncompressed LibreOffice binary
LIBRE_OFFICE_BINARY = os.path.join(LIBRE_OFFICE_PATH, "instdir/program/soffice.bin")


class DocumentExtensionError(Exception):
    pass


class DocumentConversionError(Exception):
    pass


class DocumentSizeError(Exception):
    pass


def libre_office_convert(input_filename):
    # If not already uncompressed, uncompress
    if not os.path.exists(LIBRE_OFFICE_PATH):
        with tarfile.open(LIBRE_OFFICE_ARCHIVE, "r:gz") as tar_file:
            tar_file.extractall(path=LIBRE_OFFICE_PATH)

    # Run LibreOffice
    # Adapted from https://github.com/vladgolubev/serverless-libreoffice/blob/master/src/libreoffice.js
    command = (
        f"cd {shlex.quote(LIBRE_OFFICE_PATH)} && export "
        f"HOME={shlex.quote(LIBRE_OFFICE_PATH)} && SAL_DISABLE_CPD=true "
        f"{shlex.quote(LIBRE_OFFICE_BINARY)} --headless --norestore --invisible "
        f"--nodefault --nofirststartwizard --nolockcheck --nologo --convert-to "
        f'"pdf:writer_pdf_Export" --outdir '
        f"{shlex.quote(os.path.dirname(input_filename))} "
        f"{shlex.quote(input_filename)}"
    )
    if os.system(command) != 0:
        # For unknown reasons, run twice
        # https://github.com/vladgolubev/serverless-libreoffice/blob/master/src/libreoffice.js#L19
        if os.system(command) != 0:
            raise DocumentConversionError()


def convert(input_filename, doc_id, slug):
    # Provision a temporary directory in which to handle document conversion
    document_directory = tempfile.mkdtemp(prefix=TMP_DIR)

    # Grab file from storage to tmp
    tmp_path = os.path.join(document_directory, Path(input_filename).name)
    with storage.open(input_filename, "rb") as document_file:
        with open(tmp_path, "wb") as tmp_file:
            tmp_file.write(document_file.read())

    # Run LibreOffice
    libre_office_convert(tmp_path)
    # Remove created file (early, just to free RAM that might be needed later)
    os.remove(tmp_path)

    # Put converted file back in storage
    # We expect the filename to be the same but with a pdf extension
    # (LibreOffice offers no mechanism to specify a precise name)
    output_path = str(Path(tmp_path).with_suffix(".pdf"))
    output_filename = path.doc_path(doc_id, slug)
    with storage.open(output_filename, "wb") as output_document_file:
        with open(output_path, "rb") as pdf_file:
            output_document_file.write(pdf_file.read())

    # Remove temporary directory
    shutil.rmtree(document_directory)


@pubsub_function(REDIS, DOCUMENT_CONVERT_TOPIC)
def run_document_conversion(data, _context=None):
    """Converts document passed in to PDF and triggers PDF extraction."""
    data = get_pubsub_data(data)
    doc_id = data["doc_id"]
    slug = data["slug"]
    extension = data["extension"]

    logger.info("[DOCUMENT CONVERSION] doc_id %s extension %s", doc_id, extension)

    # Ensure whitelisted file extension
    if extension.lower().strip() not in SUPPORTED_DOCUMENT_EXTENSIONS:
        raise DocumentExtensionError()

    input_file = path.original_path(doc_id, slug, extension)

    # Ensure non-PDF document size is within the limit
    if storage.size(input_file) > DOCUMENT_SIZE_LIMIT:
        # If not, remove the PDF
        storage.delete(path.path(doc_id))
        raise DocumentSizeError()

    # Run conversion
    convert(input_file, doc_id, slug)

    # Delete the original file
    storage.delete(input_file)

    # Trigger PDF processing (output file should be expected doc path)
    publisher.publish(PDF_PROCESS_TOPIC, data=encode_pubsub_data(data))
