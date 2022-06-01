# Django
from django.conf import settings
from django.contrib.auth import logout
from django.db import transaction
from django.http.response import (
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

# Standard Library
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

# DocumentCloud
from documentcloud.common.environment import storage
from documentcloud.common.extensions import EXTENSIONS
from documentcloud.core.choices import Language
from documentcloud.documents.choices import Access
from documentcloud.documents.models import Document
from documentcloud.documents.tasks import fetch_file_url, solr_index
from documentcloud.users.models import User


class FileServer(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, *args, **kwargs):
        # pylint: disable=unused-argument
        document = get_object_or_404(
            Document.objects.get_viewable(request.user), pk=kwargs["pk"]
        )
        if not document.public:
            url = document.path + kwargs["path"]
            url = storage.presign_url(url, "get_object", use_custom_domain=True)
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


@csrf_exempt
def mailgun(request):
    """Upload documents by email"""
    if not _verify(request.POST):
        return HttpResponseForbidden()

    email = request.POST["To"]
    mailkey = email.split("@", 1)[0]
    user = User.objects.get(mailkey=mailkey)

    attachments = json.loads(request.POST.get("attachments", "[]"))

    for attachment in attachments:
        with transaction.atomic():
            title, original_extension = os.path.splitext(attachment["name"])
            original_extension = original_extension.strip(".").lower()
            if original_extension not in EXTENSIONS:
                continue
            document = Document.objects.create(
                access=Access.private,
                language=Language.english,
                user=user,
                organization=user.organization,
                title=title,
                original_extension=original_extension,
            )
            transaction.on_commit(lambda d=document: solr_index.delay(d.pk))
            transaction.on_commit(
                lambda a=attachment, d=document: fetch_file_url.delay(
                    a["url"],
                    d.pk,
                    force_ocr=False,
                    auth=("api", settings.MAILGUN_API_KEY),
                )
            )
    return HttpResponse("OK")


def _verify(post):
    """Verify that the message is from mailgun"""
    token = post.get("token", "")
    timestamp = post.get("timestamp", "")
    signature = post.get("signature", "")
    signature_ = hmac.new(
        key=settings.MAILGUN_API_KEY.encode("utf8"),
        msg="{}{}".format(timestamp, token).encode("utf8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return signature == signature_ and int(timestamp) + 300 > time.time()
