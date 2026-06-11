# Django
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

# Standard Library
import hmac
import logging

# Third Party
import requests
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings
from squarelet_auth import settings as squarelet_settings
from squarelet_auth.users.utils import squarelet_update_or_create
from squarelet_auth.utils import squarelet_get

logger = logging.getLogger(__name__)


class ProcessingTokenAuthentication(BaseAuthentication):
    """Authorization for our processing functions"""

    def authenticate(self, request):
        auth = get_authorization_header(request).split()

        if not auth or auth[0].lower() != b"processing-token":
            return None

        if len(auth) == 1:
            msg = _("Invalid token header. No credentials provided.")
            raise exceptions.AuthenticationFailed(msg)
        if len(auth) > 2:
            msg = _("Invalid token header. Token string should not contain spaces.")
            raise exceptions.AuthenticationFailed(msg)

        try:
            token = auth[1].decode()
        except UnicodeError:
            msg = _(
                "Invalid token header. Token string should not contain invalid "
                "characters."
            )
            raise exceptions.AuthenticationFailed(msg)

        return self.authenticate_credentials(token)

    def authenticate_credentials(self, key):
        if hmac.compare_digest(key, settings.PROCESSING_TOKEN):
            return (AnonymousUser(), {"permissions": {"processing"}})
        else:
            raise exceptions.AuthenticationFailed(_("Invalid token."))

    def authenticate_header(self, request):
        return "processing-token"


class SquareletJWTAuthentication(JWTAuthentication):
    """JWT authentication that lazily provisions users from Squarelet.

    Squarelet issues JWTs for users who may not yet have a mirrored ``User``
    row in DocumentCloud's database. That row is normally created on first
    interactive login, or via the asynchronous cache-invalidation webhook.
    Either of these can lose a race against an immediate API call, like when
    we're trying to fetch information about a user's add-ons in Klaxon.

    When the user is missing locally we fetch their data from Squarelet
    synchronously, create the row inline, and retry, so the very first
    authenticated request is self-healing and the timing race is eliminated.

    Provisioning is gated by ``SQUARELET_DISABLE_CREATE`` (via
    ``squarelet_auth.settings.DISABLE_CREATE``), matching the webhook's
    ``pull_data`` task: where creating users from Squarelet is disabled, an
    unknown user still 401s rather than being provisioned here.
    """

    def get_user(self, validated_token):
        try:
            return super().get_user(validated_token)
        except exceptions.AuthenticationFailed as exc:
            # Only provision when the token is valid but the user simply does
            # not exist locally yet. Genuinely invalid tokens (and any other
            # failures) must still surface as a 401. simplejwt wraps its detail
            # in a dict (``{"detail": ..., "code": ...}``) while plain DRF uses
            # an ``ErrorDetail`` string, so handle both shapes.
            if isinstance(exc.detail, dict):
                code = exc.detail.get("code")
            else:
                code = getattr(exc.detail, "code", None)
            if code != "user_not_found":
                raise

            # Respect the same gate as the webhook's pull_data task: when
            # creating users from Squarelet is disabled, don't provision them
            # here either -- let the request 401.
            if squarelet_settings.DISABLE_CREATE:
                raise

            uuid = validated_token[api_settings.USER_ID_CLAIM]
            logger.info("[JWT] Lazily provisioning user from Squarelet: %s", uuid)
            try:
                resp = squarelet_get(f"/api/users/{uuid}/")
                resp.raise_for_status()
                squarelet_update_or_create(uuid, resp.json())
            except requests.exceptions.RequestException:
                logger.exception("[JWT] Failed to fetch user from Squarelet: %s", uuid)
                # Re-raise the original auth failure so the request 401s
                raise exc

            # Retry now that the user should exist locally
            return super().get_user(validated_token)
