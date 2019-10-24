# Django
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.utils.translation import ugettext_lazy as _
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

# Standard Library
import hmac


class ProcessingTokenAuthentication(BaseAuthentication):
    """Authorization for our processing functions"""

    def authenticate(self, request):
        print(request)
        print("METHOD", request.method)
        auth = get_authorization_header(request).split()

        print(auth)
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
            print("TOKEN", token)
        except UnicodeError:
            msg = _(
                "Invalid token header. Token string should not contain invalid "
                "characters."
            )
            raise exceptions.AuthenticationFailed(msg)

        return self.authenticate_credentials(token)

    def authenticate_credentials(self, key):
        print("AUTHING", key, settings.PROCESSING_TOKEN)
        if hmac.compare_digest(key, settings.PROCESSING_TOKEN):
            print("GOT USER")
            return (AnonymousUser(), {"permissions": {"processing"}})
        else:
            raise exceptions.AuthenticationFailed(_("Invalid token."))

    def authenticate_header(self, request):
        return "processing-token"
