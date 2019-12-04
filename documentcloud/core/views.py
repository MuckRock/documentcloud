# Django
from django.http.response import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.generic import View

# DocumentCloud
from documentcloud.common.environment import storage
from documentcloud.documents.models import Document


class FileServer(View):
    def get(self, request, *args, **kwargs):
        # pylint: disable=unused-argument
        document = get_object_or_404(
            Document.objects.get_viewable(request.user), pk=kwargs["pk"]
        )
        url = document.path + kwargs["path"]
        if not document.public:
            url = storage.presign_url(url, "get_object")
        if request.is_ajax():
            return JsonResponse({"location": url})
        else:
            return HttpResponseRedirect(url)
        return HttpResponseRedirect(url)
