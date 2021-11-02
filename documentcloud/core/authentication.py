# Django
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

# Standard Library
import hmac


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
