# Django
from django.http.response import Http404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

# Standard Library
from urllib.parse import unquote_plus

# Third Party
from furl import furl

# DocumentCloud
from documentcloud.oembed.registry import registry


class OEmbedView(APIView):
    """The oembed endpoint responds with the appropriate code
    allowing you to embed the resource (document, page, project, etc) on your website.
    """

    permission_classes = (AllowAny,)

    def get(self, request):

        if "url" not in request.GET:
            return Response(
                {"error": "url required"}, status=status.HTTP_400_BAD_REQUEST
            )

        def get_int(key):
            """Get the GET parameter as an integer, or return None
            if not present or not a valid integer
            """
            try:
                return int(request.GET[key])
            except (ValueError, KeyError):
                return None

        furl_url = furl(request.GET["url"])
        # remove _escaped_fragment_ if it exists
        furl_url.query.params.pop("_escaped_fragment_", None)
        # always add embed=1
        furl_url.query.params["embed"] = 1
        query = furl_url.query
        # make a copy so that query is not overwritten when we
        # set furl_url.query to None
        furl_url = furl_url.copy()
        furl_url.query = None
        url = unquote_plus(furl_url.url)

        for oembed in registry:
            for pattern in oembed.patterns:
                match = pattern.match(url)
                if match:
                    oembed_response = oembed.response(
                        request,
                        query,
                        max_width=get_int("maxwidth"),
                        max_height=get_int("maxheight"),
                        **match.groupdict()
                    )
                    return Response(oembed_response)

        raise Http404
