# Standard Library
import asyncio
import io
import mimetypes
from itertools import zip_longest

# Third Party
import boto3
import environ
import requests
import smart_open
from botocore.client import Config

# Local
from ... import access_choices

env = environ.Env()

ACLS = {
    access_choices.PUBLIC: "public-read",
    access_choices.ORGANIZATION: "private",
    access_choices.PRIVATE: "private",
    access_choices.INVISIBLE: "private",
}

AWS_RETRIES_MAX_ATTEMPTS = env.int("AWS_RETRIES_MAX_ATTEMPTS", default=10)


def grouper(iterable, num, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * num
    return zip_longest(*args, fillvalue=fillvalue)


class AwsStorage:
    def __init__(self, resource_kwargs=None, minio=False):

        self.resource_kwargs = {} if resource_kwargs is None else resource_kwargs
        if "config" not in self.resource_kwargs:
            self.resource_kwargs["config"] = Config(
                signature_version="s3v4",
                retries={"max_attempts": AWS_RETRIES_MAX_ATTEMPTS},
            )
        self.s3_resource = boto3.resource("s3", **self.resource_kwargs)
        self.s3_client = boto3.client("s3", **self.resource_kwargs)
        self.minio = minio

    def bucket_key(self, file_name):
        return file_name.split("/", 1)

    def size(self, file_name):
        bucket, key = self.bucket_key(file_name)
        bucket = self.s3_resource.Bucket(bucket)
        return bucket.Object(key).content_length

    def open(self, file_name, mode="rb", content_type=None, access=None):

        transport_params = {
            "resource_kwargs": self.resource_kwargs,
            "multipart_upload_kwargs": {},
        }

        if content_type is None:
            # attempt to guess content type if not specified
            content_type = mimetypes.guess_type(file_name)[0]

        if content_type is not None:
            # set content type if we have one
            transport_params["multipart_upload_kwargs"]["ContentType"] = content_type

        if access is not None:
            transport_params["multipart_upload_kwargs"]["ACL"] = ACLS[access]

        return smart_open.open(
            f"s3://{file_name}", mode, transport_params=transport_params
        )

    def simple_upload(
        self, file_name, contents, content_type=None, access=access_choices.PRIVATE
    ):
        bucket, key = self.bucket_key(file_name)
        extra_args = {"ACL": ACLS[access]}

        if content_type is None:
            # attempt to guess content type if not specified
            content_type = mimetypes.guess_type(file_name)[0]
        if content_type is not None:
            # set content type if we have one
            extra_args["ContentType"] = content_type

        with io.BytesIO(contents) as mem_file:
            self.s3_client.upload_fileobj(mem_file, bucket, key, ExtraArgs=extra_args)

    def async_upload(
        self, file_names, contents, content_types=None, access=access_choices.PRIVATE
    ):
        """Upload given files in parallel"""
        # import aioboto3 locally to avoid needing it installed on lambda
        # Third Party
        import aioboto3

        if content_types is None:
            content_types = [None for _ in range(len(file_names))]

        async def main():
            session = aioboto3.Session()
            async with session.client("s3", **self.resource_kwargs) as as3_client:
                tasks = []
                for file_name, content, content_type in zip(
                    file_names, contents, content_types
                ):
                    bucket, key = self.bucket_key(file_name)
                    extra_args = {"ACL": ACLS[access]}
                    if content_type is None:
                        # attempt to guess content type if not specified
                        content_type = mimetypes.guess_type(file_name)[0]
                    if content_type is not None:
                        # set content type if we have one
                        extra_args["ContentType"] = content_type

                    tasks.append(
                        as3_client.upload_fileobj(
                            io.BytesIO(content), bucket, key, ExtraArgs=extra_args
                        )
                    )

                await asyncio.gather(*tasks)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())

    def presign_url(self, file_name, method_name, use_custom_domain=False):

        if (
            use_custom_domain
            and method_name == "get_object"
            and env.bool("AWS_SIGN_USE_CUSTOM_DOMAIN", default=False)
        ):
            # hack to use custom domain
            return self._presign_url_custom(file_name)

        bucket, key = self.bucket_key(file_name)
        return self.s3_client.generate_presigned_url(
            method_name, Params={"Bucket": bucket, "Key": key}, ExpiresIn=300
        )

    def _presign_url_custom(self, file_name):
        """This is very hacky way to get boto3 to produce the correct
        presigned URL with a custom domain name, instead of using an
        AWS domain.  Using the custom domain lets us use the CloudFlare CDN
        """
        # Django
        from django.conf import settings

        resource_kwargs = {
            **self.resource_kwargs,
            "config": Config(
                signature_version="s3v4",
                retries={"max_attempts": AWS_RETRIES_MAX_ATTEMPTS},
                s3={"addressing_style": "path"},
            ),
        }
        s3_client = boto3.client("s3", **resource_kwargs)

        bucket, key = self.bucket_key(file_name)
        request_dict = {
            "context": {
                "is_presign_request": True,
                "use_global_endpoint": True,
                "signing": {"bucket": bucket},
            },
            "headers": {},
            "method": "GET",
            "query_string": {},
            "url": f"{settings.PUBLIC_ASSET_URL}{key}",
            "url_path": key,
            "body": b"",
        }
        # pylint: disable=protected-access
        return s3_client._request_signer.generate_presigned_url(
            request_dict, "GetObject", expires_in=300
        )

    def exists(self, file_name):
        # https://www.peterbe.com/plog/fastest-way-to-find-out-if-a-file-exists-in-s3
        bucket, key = self.bucket_key(file_name)
        response = self.s3_client.list_objects_v2(Bucket=bucket, Prefix=key)
        for obj in response.get("Contents", []):
            if obj["Key"] == key:
                return True
        return False

    def fetch_url(self, url, file_name, access, auth=None):
        with self.open(file_name, "wb", access=access) as out_file, requests.get(
            url, stream=True, auth=auth
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=10 * 1024 * 1024):
                out_file.write(chunk)

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
        bucket, prefix = self.bucket_key(file_prefix)
        bucket = self.s3_resource.Bucket(bucket)
        for obj in bucket.objects.filter(Prefix=prefix):
            obj.Acl().put(ACL=ACLS[access])

    def set_access(self, file_names, access):
        """Set access for given keys"""
        if self.minio:
            # minio does not support object ACLs
            return
        for file_name in file_names:
            bucket, key = self.bucket_key(file_name)
            object_acl = self.s3_resource.ObjectAcl(bucket, key)
            object_acl.put(ACL=ACLS[access])

    def async_set_access(self, file_names, access):
        """Set access for given keys asynchronously"""
        # import aioboto3 locally to avoid needing it installed on lambda
        # Third Party
        import aioboto3

        if self.minio:
            # minio does not support object ACLs
            return

        async def main():
            session = aioboto3.Session()
            async with session.resource("s3", **self.resource_kwargs) as as3_resource:
                tasks = []
                for file_name in file_names:
                    bucket, key = self.bucket_key(file_name)
                    object_acl = await as3_resource.ObjectAcl(bucket, key)
                    tasks.append(object_acl.put(ACL=ACLS[access]))
                await asyncio.gather(*tasks)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())

    def async_download(self, file_names):
        """Download given files in parallel"""
        # import aioboto3 locally to avoid needing it installed on lambda
        # Third Party
        import aioboto3

        data = [io.BytesIO() for _ in file_names]

        async def main():
            session = aioboto3.Session()
            async with session.client("s3", **self.resource_kwargs) as as3_client:
                tasks = []
                for file_name, datum in zip(file_names, data):
                    bucket, key = self.bucket_key(file_name)
                    tasks.append(as3_client.download_fileobj(bucket, key, datum))
                await asyncio.gather(*tasks, return_exceptions=True)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())

        return_data = []
        for datum in data:
            datum.seek(0)
            return_data.append(datum.read())
        return return_data

    def async_size(self, file_names):
        """Get the size of the given files in parallel"""
        # import aioboto3 locally to avoid needing it installed on lambda
        # Third Party
        import aioboto3

        async def main():
            session = aioboto3.Session()
            async with session.resource("s3", **self.resource_kwargs) as as3_resource:
                tasks = []
                for file_name in file_names:
                    bucket, key = self.bucket_key(file_name)
                    object_ = await as3_resource.Object(bucket, key)
                    tasks.append(object_.content_length)
                return await asyncio.gather(*tasks, return_exceptions=True)

        loop = asyncio.get_event_loop()
        sizes = loop.run_until_complete(main())
        return [0 if isinstance(s, Exception) else s for s in sizes]

    def list(self, file_prefix, marker=None, limit=None):
        """List files in the given path
        marker if given will start from after that file
        limit will set a max on the number of files returned
        """
        if marker is None:
            marker = ""
        else:
            # strip the bucket from the marker
            _, marker = self.bucket_key(marker)

        bucket, prefix = self.bucket_key(file_prefix)
        bucket = self.s3_resource.Bucket(bucket)
        objects = bucket.objects.filter(Prefix=prefix, Marker=marker)
        if limit is not None:
            objects = objects.limit(limit)
        return [f"{bucket.name}/{o.key}" for o in objects]


storage = AwsStorage()
