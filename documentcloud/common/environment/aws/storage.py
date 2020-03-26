# Standard Library
import io
import mimetypes

# Third Party
import boto3
import environ
import requests
import smart_open
from botocore.client import Config

env = environ.Env()


class AwsStorage:
    def __init__(self, resource_kwargs=None, minio=False):

        self.resource_kwargs = {} if resource_kwargs is None else resource_kwargs
        if "config" not in self.resource_kwargs:
            self.resource_kwargs["config"] = Config(signature_version="s3v4")
        self.s3_resource = boto3.resource("s3", **self.resource_kwargs)
        self.s3_client = boto3.client("s3", **self.resource_kwargs)
        self.minio = minio

    def bucket_key(self, file_name):
        return file_name.split("/", 1)

    def size(self, file_name):
        bucket, key = self.bucket_key(file_name)
        bucket = self.s3_resource.Bucket(bucket)
        return bucket.Object(key).content_length

    def open(self, file_name, mode="rb", content_type=None):

        transport_params = {"resource_kwargs": self.resource_kwargs}

        if content_type is None:
            # attempt to guess content type if not specified
            content_type = mimetypes.guess_type(file_name)[0]

        if content_type is not None:
            # set content type if we have one
            transport_params["multipart_upload_kwargs"] = {"ContentType": content_type}

        return smart_open.open(
            f"s3://{file_name}", mode, transport_params=transport_params
        )

    def simple_upload(self, file_name, contents, content_type=None):
        bucket, key = self.bucket_key(file_name)

        if content_type is None:
            # attempt to guess content type if not specified
            content_type = mimetypes.guess_type(file_name)[0]
        if content_type is not None:
            # set content type if we have one
            extra_args = {"ContentType": content_type}
        else:
            extra_args = {}

        with io.BytesIO(contents) as mem_file:
            self.s3_client.upload_fileobj(mem_file, bucket, key, ExtraArgs=extra_args)

    def presign_url(self, file_name, method_name):
        bucket, key = self.bucket_key(file_name)
        return self.s3_client.generate_presigned_url(
            method_name, Params={"Bucket": bucket, "Key": key}, ExpiresIn=300
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
            response.raise_for_status()
            self.s3_resource.Bucket(bucket).upload_fileobj(response.raw, key)

    def delete(self, file_prefix):
        bucket, prefix = self.bucket_key(file_prefix)
        bucket = self.s3_resource.Bucket(bucket)
        keys = [{"Key": obj.key} for obj in bucket.objects.filter(Prefix=prefix)]
        # can only delete 1000 at a time
        key_chunks = [keys[i : i + 1000] for i in range(0, len(keys), 1000)]
        for chunk in key_chunks:
            bucket.delete_objects(Delete={"Objects": chunk})

    def set_access_path(self, file_prefix, access):
        """Set access for all keys with a given prefix"""
        if self.minio:
            # minio does not support object ACLs
            return
        acls = {"public": "public-read", "private": "private"}
        bucket, prefix = self.bucket_key(file_prefix)
        bucket = self.s3_resource.Bucket(bucket)
        for obj in bucket.objects.filter(Prefix=prefix):
            obj.Acl().put(ACL=acls[access])

    def set_access(self, file_name, access):
        """Set access for a key"""
        if self.minio:
            # minio does not support object ACLs
            return
        acls = {"public": "public-read", "private": "private"}
        bucket, key = self.bucket_key(file_name)
        object_acl = self.s3_resource.ObjectAcl(bucket, key)
        object_acl.put(ACL=acls[access])

    def list(self, file_prefix, marker="", limit=None):
        """List files in the given path
        marker if given will start from after that file
        limit will set a max on the number of files returned
        """
        bucket, prefix = self.bucket_key(file_prefix)
        bucket = self.s3_resource.Bucket(bucket)
        objects = bucket.objects.filter(Prefix=prefix, Marker=marker)
        if limit is not None:
            objects = objects.limit(limit)
        return [f"{bucket.name}/{o.key}" for o in objects]


storage = AwsStorage()
