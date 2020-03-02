"""
Backend to support OIDC login
"""

# Django
from django.conf import settings

# Third Party
from social_core.backends.open_id_connect import OpenIdConnectAuth


class SquareletBackend(OpenIdConnectAuth):
    """Authentication Backend for Squarelet OpenId"""

    # pylint: disable=abstract-method
    name = "squarelet"
    OIDC_ENDPOINT = settings.SQUARELET_URL + "/openid"

    def auth_allowed(self, response, details):
        if settings.WHITELIST_VERIFIED_JOURNALISTS:
            return any(o["verified_journalist"] for o in response["organizations"])
        else:
            return True
