# Standard Library
import base64
import json

# Third Party
import environ

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


if environment == "local":
    from documentcloud.environment.storage import storage
    from documentcloud.environment.pubsub import publisher
    from documentcloud.environment.httpsub import httpsub
elif environment == "gcp":
    import gcsfs
    from google.cloud import pubsub_v1
    import requests as httpsub

    storage = gcsfs.GCSFileSystem()
    publisher = pubsub_v1.PublisherClient()
elif environment == "aws":
    import boto3
    import smart_open
    import requests as httpsub

    s3 = boto3.resource("s3")
    sns = boto3.client("sns")

    class AwsStorage:
        @staticmethod
        def canonical(filename):
            return "s3://" + filename

        @staticmethod
        def du(filename):
            parts = filename.split("/")
            bucket = parts[0]
            file_part = "/".join(parts[1:])
            bucket = s3.Bucket(bucket)
            return {filename: bucket.Object(file_part).content_length}

        @staticmethod
        def open(filename, mode="rb"):
            return smart_open.open(AwsStorage.canonical(filename), mode)

    arn_prefix = env.str("AWS_ARN_PREFIX")

    class AwsPubsub:
        @staticmethod
        def topic_path(namespace, name):
            return ":".join([arn_prefix, name])

        @staticmethod
        def publish(topic_path, data):
            decoded_data = json.loads(data.decode("utf8"))
            sns.publish(TopicArn=topic_path, Message=data.decode("utf8"))

    storage = AwsStorage
    publisher = AwsPubsub
elif environment == "local-minio":
    import boto3
    from botocore.client import Config
    import smart_open

    resource_kwargs = {
        "endpoint_url": "http://documentcloud_minio:9000",
        "config": Config(signature_version="s3v4"),
        "region_name": "us-east-1",
    }

    s3 = boto3.resource("s3", **resource_kwargs)

    # XXX de dupe code with above?
    class AwsStorage:
        @staticmethod
        def canonical(filename):
            return "s3://" + filename

        @staticmethod
        def du(filename):
            parts = filename.split("/")
            bucket = parts[0]
            file_part = "/".join(parts[1:])
            bucket = s3.Bucket(bucket)
            return {filename: bucket.Object(file_part).content_length}

        @staticmethod
        def open(filename, mode="rb"):
            return smart_open.open(
                AwsStorage.canonical(filename), mode, resource_kwargs=resource_kwargs
            )

    from documentcloud.environment.pubsub import publisher
    from documentcloud.environment.httpsub import httpsub

else:
    raise Exception("Invalid environment")
