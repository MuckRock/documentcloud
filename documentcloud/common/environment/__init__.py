"""
Environment abstraction

This abstracts file storage and serverless function triggering, to allow our code
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


if environment == "local-minio":
    from .minio.storage import storage
    from .local.pubsub import publisher
    from .local.httpsub import httpsub
    from .local.data import get_http_data, get_pubsub_data, encode_pubsub_data
    from .local.processing_token import processing_auth

elif environment == "local-s3":
    from .aws.storage import storage
    from .local.pubsub import publisher
    from .local.httpsub import httpsub
    from .local.data import get_http_data, get_pubsub_data, encode_pubsub_data
    from .local.processing_token import processing_auth

elif environment == "local":
    from .local.storage import storage
    from .local.pubsub import publisher
    from .local.httpsub import httpsub
    from .local.data import get_http_data, get_pubsub_data, encode_pubsub_data
    from .local.processing_token import processing_auth

elif environment == "aws":
    from .aws.storage import storage
    from .aws.pubsub import publisher
    from .aws.httpsub import httpsub
    from .aws.data import get_http_data, get_pubsub_data, encode_pubsub_data
    from .aws.processing_token import processing_auth

elif environment == "gcp":
    from .gcp.storage import storage
    from .gcp.pubsub import publisher
    from .gcp.httpsub import httpsub
    from .gcp.data import get_http_data, get_pubsub_data, encode_pubsub_data
    from .gcp.processing_token import processing_auth

    raise RuntimeError("GCP environment is not currently supported")
else:
    raise RuntimeError(f"Invalid environment: {environment}")
