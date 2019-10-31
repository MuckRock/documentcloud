"""
Environment abstraction

This abstracts file storage and serverless function trigering, to allow our code
to work both locally and in different cloud environments.  This code will be run from
serverless functions not within a Django context, so no Django code is imported for
non-local environments.  We also keep all non-local code in this single file so we do
not need to copy multiple files into the serverless function context.
"""

# We do some weird things with imports to support this abstraction, silence pylint:
# pylint: disable=reimported, unused-import, ungrouped-imports

# Standard Library
import base64
import json

# Third Party
import environ
import requests

env = environ.Env()
environment = env.str("ENVIRONMENT")


def get_http_data(request):
    """Extract data from an HTTP request that works across environments."""
    if hasattr(request, "get_json"):
        # Object is a request object
        return request.get_json()
    elif "body" in request:
        # Object is an AWS LambdaContext object
        return json.loads(request["body"])
    else:
        # Object is plain JSON
        return request


def get_pubsub_data(data):
    """Extract data from a pubsub request that works across environments."""
    if "Records" in data:
        return json.loads(data["Records"][0]["Sns"]["Message"])
    else:
        return json.loads(base64.b64decode(data["data"]).decode("utf-8"))


class AwsPubsub:
    def __init__(self):
        import boto3

        self.arn_prefix = env.str("AWS_ARN_PREFIX")
        self.sns = boto3.client("sns")

    def topic_path(self, _namespace, name):
        return f"{self.arn_prefix}:{name}"

    def publish(self, topic_path, data):
        self.sns.publish(TopicArn=topic_path, Message=data.decode("utf8"))


class AwsStorage:
    def __init__(self, resource_kwargs=None):
        import boto3

        self.resource_kwargs = {} if resource_kwargs is None else resource_kwargs
        self.s3_resource = boto3.resource("s3", **self.resource_kwargs)
        self.s3_client = boto3.client("s3", **self.resource_kwargs)

    def bucket_key(self, file_name):
        return file_name.split("/", 1)

    def size(self, file_name):
        bucket, key = self.bucket_key(file_name)
        bucket = self.s3_resource.Bucket(bucket)
        return bucket.Object(key).content_length

    def open(self, file_name, mode="rb"):
        import smart_open

        return smart_open.open(
            f"s3://{file_name}",
            mode,
            transport_params={"resource_kwargs": self.resource_kwargs},
        )

    def presign_url(self, file_name):
        bucket, key = self.bucket_key(file_name)
        return self.s3_client.generate_presigned_url(
            "put_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=300
        )

    def exists(self, file_name):
        # https://www.peterbe.com/plog/fastest-way-to-find-out-if-a-file-exists-in-s3
        bucket, key = self.bucket_key(file_name)
        response = self.s3_client.list_objects_v2(Bucket=bucket, Prefix=key)
        for obj in response.get("Contents", []):
            if obj["Key"] == key:
                return True
        return False

    def fetch_url(self, url, file_name):
        bucket, key = self.bucket_key(file_name)
        with requests.get(url, stream=True) as response:
            self.s3_resource.Bucket(bucket).upload_fileobj(response.raw, key)


if environment == "local":
    from botocore.client import Config

    storage = AwsStorage(
        {
            "endpoint_url": "http://minio.documentcloud.org:9000",
            "aws_access_key_id": env.str("MINIO_ACCESS_KEY"),
            "aws_secret_access_key": env.str("MINIO_SECRET_KEY"),
            "config": Config(signature_version="s3v4"),
            "region_name": "us-east-1",
        }
    )
    from documentcloud.environment.pubsub import publisher
    from documentcloud.environment.httpsub import httpsub

elif environment == "aws":
    import requests as httpsub

    storage = AwsStorage()
    publisher = AwsPubsub()

elif environment == "gcp":
    import gcsfs
    from google.cloud import pubsub_v1
    import requests as httpsub

    storage = gcsfs.GCSFileSystem()
    publisher = pubsub_v1.PublisherClient()
    raise RuntimeError("GCP environment is not currently supported")
else:
    raise RuntimeError(f"Invalid environment: {environment}")
