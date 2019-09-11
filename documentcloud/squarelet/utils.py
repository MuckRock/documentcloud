# Django
from django.conf import settings
from django.core.cache import cache

# Standard Library
import logging

# Third Party
import requests

logger = logging.getLogger(__name__)


def get_squarelet_access_token():
    """Get an access token for squarelet"""

    # if not in cache, lock, acquire token, put in cache
    access_token = cache.get("squarelet_access_token")
    if access_token is None:
        with cache.lock("squarelt_access_token"):
            access_token = cache.get("squarelet_access_token")
            if access_token is None:
                token_url = f"{settings.SQUARELET_URL}/openid/token"
                auth = (
                    settings.SOCIAL_AUTH_SQUARELET_KEY,
                    settings.SOCIAL_AUTH_SQUARELET_SECRET,
                )
                data = {"grant_type": "client_credentials"}
                headers = {"X-Bypass-Rate-Limit": settings.BYPASS_RATE_LIMIT_SECRET}
                logger.info(token_url)
                resp = requests.post(token_url, data=data, auth=auth, headers=headers)
                resp.raise_for_status()
                resp_json = resp.json()
                access_token = resp_json["access_token"]
                # expire a few seconds early to ensure its not expired
                # when we try to use it
                expires_in = int(resp_json["expires_in"]) - 10
                cache.set("squarelet_access_token", access_token, expires_in)
    return access_token


def _squarelet(method, path, **kwargs):
    """Helper function for squarelet requests"""
    api_url = f"{settings.SQUARELET_URL}{path}"
    access_token = get_squarelet_access_token()
    headers = {
        "Authorization": "Bearer {}".format(access_token),
        "X-Bypass-Rate-Limit": settings.BYPASS_RATE_LIMIT_SECRET,
    }
    return method(api_url, headers=headers, **kwargs)


def squarelet_post(path, data):
    """Make a post request to squarlet"""
    return _squarelet(requests.post, path, data=data)


def squarelet_get(path, params=None):
    """Make a get request to squarlet"""
    if params is None:
        params = {}
    return _squarelet(requests.get, path, params=params)
