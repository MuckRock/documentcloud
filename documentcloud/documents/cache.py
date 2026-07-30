"""CDN cache invalidation for documents (CloudFront + Cloudflare)."""

# Django
from django.conf import settings

# Standard Library
import logging
import uuid

# Third Party
import boto3
import requests

logger = logging.getLogger(__name__)


def _chunk(items, size):
    """Yield successive `size`-length chunks of `items`."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _invalidate_cloudfront(paths):
    """Invalidate the given paths from CloudFront in one batch."""
    distribution_id = settings.CLOUDFRONT_DISTRIBUTION_ID
    if not distribution_id or not paths:
        return
    cloudfront = boto3.client("cloudfront")
    cloudfront.create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={
            "Paths": {"Quantity": len(paths), "Items": paths},
            "CallerReference": str(uuid.uuid4()),
        },
    )


def _invalidate_cloudflare(files=None, tags=None):
    """Purge the given files and tags from Cloudflare.

    `files` and `tags` cannot be combined in a single purge request (the zone
    purge API is a `oneOf`), so they are sent as separate requests, each
    chunked to the plan's per-request operation cap.
    """
    zone = settings.CLOUDFLARE_API_ZONE
    if not zone:
        return
    url = f"https://api.cloudflare.com/client/v4/zones/{zone}/purge_cache"
    headers = {
        "X-Auth-Email": settings.CLOUDFLARE_API_EMAIL,
        "X-Auth-Key": settings.CLOUDFLARE_API_KEY,
    }
    for key, values in (("files", files), ("tags", tags)):
        for chunk in _chunk(values or [], settings.CLOUDFLARE_PURGE_LIMIT):
            requests.post(url, json={key: chunk}, headers=headers, timeout=10)


def invalidate_cache_batch(documents):
    """Invalidate the CloudFront and Cloudflare caches for many documents.

    Cloudflare purges the API responses by Cache-Tag (`doc-{id}`) and the
    frontend pages + public asset by URL; the two are mutually exclusive in a
    single zone purge request, so they go in separate (chunked) requests.
    CloudFront purges the underlying document file by path.
    """
    documents = list(documents)
    if not documents:
        return
    logger.info("Invalidating cache for %s", [document.pk for document in documents])

    cloudfront_paths = []
    cloudflare_files = []
    cloudflare_tags = []
    for document in documents:
        # the doc path without the s3 bucket name
        doc_path = document.doc_path[document.doc_path.index("/") :]
        cloudfront_paths.append(doc_path)
        # always purge the frontend URLs: on a public -> private flip `access`
        # is already private by now, but the public copy may still be cached at
        # the edge - purging a URL that was never cached is harmless
        cloudflare_files.extend(
            host + document.get_absolute_url() for host in settings.CLOUDFLARE_HOSTS
        )
        cloudflare_files.append(settings.PUBLIC_ASSET_URL + doc_path[1:])
        cloudflare_tags.append(document.cache_tag)

    _invalidate_cloudfront(cloudfront_paths)
    _invalidate_cloudflare(files=cloudflare_files, tags=cloudflare_tags)
