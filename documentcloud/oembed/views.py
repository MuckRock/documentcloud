# Django
from django.http.response import Http404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

# DocumentCloud
from documentcloud.oembed.registry import registry


class OEmbedView(APIView):
    """oEmbed endpoint"""

    permission_classes = (AllowAny,)

    def get(self, request):

        if "url" not in request.GET:
            return Response(
                {"error": "url required"}, status=status.HTTP_400_BAD_REQUEST
            )

        for oembed in registry:
            for pattern in oembed.patterns:
                match = pattern.match(request.GET["url"])
                if match:
                    oembed_response = oembed.response(request, **match.groupdict())
                    return Response(oembed_response)

        raise Http404
