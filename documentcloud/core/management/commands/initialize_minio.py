# Django
from django.core.management.base import BaseCommand

# Standard Library
import json

# Third Party
import boto3
import environ
from botocore.client import Config
from botocore.exceptions import ClientError

env = environ.Env()


class Command(BaseCommand):
    help = "Initialize Minio buckets and policies for local development"

    def handle(self, *args, **options):
        if env.str("ENVIRONMENT") != "local-minio":
            return

        client = boto3.client(
            "s3",
            endpoint_url=env.str("MINIO_URL"),
            aws_access_key_id=env.str("MINIO_ROOT_USER"),
            aws_secret_access_key=env.str("MINIO_ROOT_PASSWORD"),
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )

        for bucket in ["documents", "ocr-languages"]:
            self._ensure_bucket(client, bucket)

        self.stdout.write("Minio initialized successfully")

    def _ensure_bucket(self, client, bucket):
        # Create bucket if it doesn't exist
        try:
            client.head_bucket(Bucket=bucket)
            self.stdout.write(f"Bucket {bucket} already exists")
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":  # Bucket doesn't exist, create it
                client.create_bucket(Bucket=bucket)
                self.stdout.write(f"Created {bucket} bucket")
            else:
                raise

        # Set public read policy
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket}/*",
                }
            ],
        }
        client.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
