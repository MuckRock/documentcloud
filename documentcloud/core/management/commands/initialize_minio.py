import json
import boto3
import environ
from botocore.client import Config
from botocore.exceptions import ClientError
from django.core.management.base import BaseCommand

env = environ.Env()


class Command(BaseCommand):
    help = "Initialize Minio bucket and policies for local development"

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

        # Create bucket if it doesn't exist
        try:
            client.head_bucket(Bucket="documents")
            self.stdout.write("Bucket already exists")
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404": # Bucket doesn't exist, create it
                client.create_bucket(Bucket="documents")
                self.stdout.write("Created documents bucket")
            else:
                raise

        # Set public read policy
        policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": "arn:aws:s3:::documents/*"
            }]
        }
        client.put_bucket_policy(Bucket="documents", Policy=json.dumps(policy))
        self.stdout.write("Minio initialized successfully")