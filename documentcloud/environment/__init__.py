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


# Third Party
import environ

env = environ.Env()
environment = env.str("ENVIRONMENT")


class RedisFields:
    @staticmethod
    def images_remaining(doc_id):
        return f"{doc_id}:image"

    @staticmethod
    def texts_remaining(doc_id):
        return f"{doc_id}:text"

    @staticmethod
    def page_count(doc_id):
        return f"{doc_id}:pages"

    @staticmethod
    def dimensions(doc_id):
        return f"{doc_id}:dimensions"

    @staticmethod
    def page_dimension(doc_id, page_dimension):
        return f"{doc_id}:dim{page_dimension}"

    @staticmethod
    def image_bits(doc_id):
        return f"{doc_id}:imageBits"

    @staticmethod
    def text_bits(doc_id):
        return f"{doc_id}:textBits"


if environment == "local-minio":
    from .aws.storage import minio_storage as storage
    from .local.pubsub import publisher
    from .local.httpsub import httpsub
    from .local.data import get_http_data, get_pubsub_data

elif environment == "local-s3":
    from .aws.storage import storage
    from .local.pubsub import publisher
    from .local.httpsub import httpsub
    from .local.data import get_http_data, get_pubsub_data

elif environment == "local":
    from .local.storage import storage
    from .local.pubsub import publisher
    from .local.httpsub import httpsub
    from .local.data import get_http_data, get_pubsub_data

elif environment == "aws":
    from .aws.storage import storage
    from .aws.pubsub import publisher
    from .aws.httpsub import httpsub
    from .aws.data import get_http_data, get_pubsub_data

elif environment == "gcp":
    from .gcp.storage import storage
    from .gcp.pubsub import publisher
    from .gcp.httpsub import httpsub
    from .gcp.data import get_http_data, get_pubsub_data

    raise RuntimeError("GCP environment is not currently supported")
else:
    raise RuntimeError(f"Invalid environment: {environment}")
