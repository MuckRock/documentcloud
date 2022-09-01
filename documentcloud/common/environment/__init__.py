"""
Environment abstraction

This abstracts file storage and serverless function triggering, to allow our code
to work both locally and in different cloud environments.  This code will be run from
serverless functions not within a Django context, so no Django code is imported for
non-local environments.  We also keep all non-local code in this single file so we do
not need to copy multiple files into the serverless function context.
"""

# Third Party
import environ

env = environ.Env()
environment = env.str("ENVIRONMENT")


if environment == "local-minio":
    # Local
    from .local.data import (
        encode_pubsub_data,
        encode_response,
        get_http_data,
        get_pubsub_data,
    )
    from .local.httpsub import httpsub
    from .local.processing_token import processing_auth
    from .local.pubsub import publisher
    from .minio.storage import storage

elif environment == "local-s3":
    # Local
    from .aws.storage import storage
    from .local.data import (
        encode_pubsub_data,
        encode_response,
        get_http_data,
        get_pubsub_data,
    )
    from .local.httpsub import httpsub
    from .local.processing_token import processing_auth
    from .local.pubsub import publisher

elif environment == "local":
    # Local
    from .local.data import (
        encode_pubsub_data,
        encode_response,
        get_http_data,
        get_pubsub_data,
    )
    from .local.httpsub import httpsub
    from .local.processing_token import processing_auth
    from .local.pubsub import publisher
    from .local.storage import storage

elif environment == "aws":
    # Local
    from .aws.data import (
        encode_pubsub_data,
        encode_response,
        get_http_data,
        get_pubsub_data,
    )
    from .aws.httpsub import httpsub
    from .aws.processing_token import processing_auth
    from .aws.pubsub import publisher
    from .aws.storage import storage

elif environment == "gcp":
    # Local
    from .gcp.data import (
        encode_pubsub_data,
        encode_response,
        get_http_data,
        get_pubsub_data,
    )
    from .gcp.httpsub import httpsub
    from .gcp.processing_token import processing_auth
    from .gcp.pubsub import publisher
    from .gcp.storage import storage

    raise RuntimeError("GCP environment is not currently supported")
else:
    raise RuntimeError(f"Invalid environment: {environment}")
