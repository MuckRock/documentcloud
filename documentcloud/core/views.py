# Django
from django.http.response import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.views.generic import View

# DocumentCloud
from documentcloud.documents.models import Document
from documentcloud.environment import storage


class FileServer(View):
    def get(self, request, *args, **kwargs):
        document = get_object_or_404(
            Document.objects.get_viewable(request.user), pk=kwargs["pk"]
        )
        url = document.path + kwargs["path"]
        if not document.public:
            url = storage.presign_url(url, "get_object")
        return HttpResponseRedirect(url)
