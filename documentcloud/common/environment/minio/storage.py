# Third Party
import environ
from botocore.client import Config

# Local
from ..aws.storage import AwsStorage

env = environ.Env()


class MinIOStorage(AwsStorage):
    def __init__(self, resource_kwargs=None, minio=True):
        if resource_kwargs is None:
            resource_kwargs = {
                "endpoint_url": env.str("MINIO_URL"),
                "aws_access_key_id": env.str("MINIO_ACCESS_KEY"),
                "aws_secret_access_key": env.str("MINIO_SECRET_KEY"),
                "config": Config(signature_version="s3v4"),
                "region_name": "us-east-1",
            }
        super().__init__(resource_kwargs, minio)


storage = MinIOStorage()
