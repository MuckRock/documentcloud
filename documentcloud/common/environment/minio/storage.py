# Standard Library
import base64
import hashlib

# Third Party
import environ
from botocore.client import Config

# Local
from ..aws.storage import AwsStorage

env = environ.Env()


def _add_content_md5(params, **_kwargs):
    """boto3 >= 1.36 sends a CRC32 checksum instead of Content-MD5 for
    operations that require a checksum (e.g. DeleteObjects), but older MinIO
    releases reject those requests with MissingContentMD5. Add it back.
    """
    body = params.get("body") or b""
    if isinstance(body, str):
        body = body.encode("utf-8")
    params["headers"]["Content-MD5"] = base64.b64encode(
        hashlib.md5(body).digest()
    ).decode("ascii")


class MinIOStorage(AwsStorage):
    def __init__(self, resource_kwargs=None, minio=True):
        if resource_kwargs is None:
            resource_kwargs = {
                "endpoint_url": env.str("MINIO_URL"),
                "aws_access_key_id": env.str("MINIO_ROOT_USER"),
                "aws_secret_access_key": env.str("MINIO_ROOT_PASSWORD"),
                "config": Config(signature_version="s3v4"),
                "region_name": "us-east-1",
            }
        super().__init__(resource_kwargs, minio)
        for client in (self.s3_client, self.s3_resource.meta.client):
            client.meta.events.register(
                "before-call.s3.DeleteObjects", _add_content_md5
            )


storage = MinIOStorage()
