# Django
from django.core.management.base import BaseCommand, CommandError

# Standard Library
import os

# DocumentCloud
from documentcloud.common.environment import storage

TESSERACT_DATA_DIRECTORY = "documentcloud/documents/processing/ocr/tesseract/tessdata/"
MINIO_DATA_DIRECTORY = "ocr-languages"


class Command(BaseCommand):
    """Uploads tesseract language data into minio for local development"""

    help = "Uploads tesseract language data into minio"

    def handle(self, *args, **options):
        data_files = os.listdir(TESSERACT_DATA_DIRECTORY)
        print("UPLOADING", data_files)
        print("...")
        for data_file_path in data_files:
            with open(
                os.path.join(TESSERACT_DATA_DIRECTORY, data_file_path), "rb"
            ) as data_file:
                with storage.open(
                    os.path.join(MINIO_DATA_DIRECTORY, data_file_path), "wb"
                ) as minio_file:
                    minio_file.write(data_file.read())

        print("WROTE ALL FILES")
