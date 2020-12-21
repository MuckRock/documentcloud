# Django
from django.conf import settings
from django.contrib.auth import logout
from django.http.response import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

# Standard Library
from urllib.parse import urlencode

# DocumentCloud
from documentcloud.common.environment import storage
from documentcloud.documents.models import Document


class FileServer(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, *args, **kwargs):
        # pylint: disable=unused-argument
        document = get_object_or_404(
            Document.objects.get_viewable(request.user), pk=kwargs["pk"]
        )
        if not document.public:
            url = document.path + kwargs["path"]
            url = storage.presign_url(url, "get_object")
        else:
            url = (
                f"{settings.PUBLIC_ASSET_URL}documents/{kwargs['pk']}/{kwargs['path']}"
            )

        if request.META.get("HTTP_ACCEPT", "").startswith("application/json"):
            return JsonResponse({"location": url})
        else:
            return HttpResponseRedirect(url)


def account_logout(request):
    """Logs a user out of their account and redirects to squarelet's logout page"""
    url = settings.DOCCLOUD_URL + "/"
    if "id_token" in request.session:
        params = {
            "id_token_hint": request.session["id_token"],
            "post_logout_redirect_uri": url,
        }
        redirect_url = "{}/openid/end-session?{}".format(
            settings.SQUARELET_URL, urlencode(params)
        )
    else:
        redirect_url = url
    logout(request)
    return redirect(redirect_url)
