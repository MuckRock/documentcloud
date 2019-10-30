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
    import requests

    resource_kwargs = {
        "endpoint_url": "http://minio.documentcloud.org:9000",
        "aws_access_key_id": env.str("MINIO_ACCESS_KEY"),
        "aws_secret_access_key": env.str("MINIO_SECRET_KEY"),
        "config": Config(signature_version="s3v4"),
        "region_name": "us-east-1",
    }

    s3 = boto3.resource("s3", **resource_kwargs)
    s3_client = boto3.client("s3", **resource_kwargs)

    # XXX de dupe code with above?
    # rework this abstraction - not just based on gcsfs code
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
                AwsStorage.canonical(filename),
                mode,
                transport_params={"resource_kwargs": resource_kwargs},
            )

        @staticmethod
        def presign_url(key):
            return s3_client.generate_presigned_url(
                "put_object",
                Params={"Bucket": env.str("UPLOAD_BUCKET"), "Key": key},
                ExpiresIn=300,
            )

        @staticmethod
        def copy(src_bucket, src_key, dst_bucket, dst_key):
            return s3.meta.client.copy(
                {"Bucket": src_bucket, "Key": src_key}, dst_bucket, dst_key
            )

        @staticmethod
        def exists(bucket, key):
            # https://www.peterbe.com/plog/fastest-way-to-find-out-if-a-file-exists-in-s3
            response = s3_client.list_objects_v2(Bucket=bucket, Prefix=key)
            for obj in response.get("Contents", []):
                if obj["Key"] == key:
                    return True
            return False

        @staticmethod
        def fetch_url(url, bucket, key):
            response = requests.get(url, stream=True)
            s3.Bucket(bucket).upload_fileobj(response.raw, key)

    storage = AwsStorage
    from documentcloud.environment.pubsub import publisher
    from documentcloud.environment.httpsub import httpsub

else:
    raise Exception("Invalid environment")
