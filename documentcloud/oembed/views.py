# Django
from django.http.response import Http404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

# Standard Library
from urllib.parse import unquote_plus

# Third Party
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from furl import furl

# DocumentCloud
from documentcloud.oembed.registry import registry


class OEmbedView(APIView):
    """The oembed endpoint responds with the appropriate code
    allowing you to embed the resource (document, page, project, etc) on your website.
    """

    permission_classes = (AllowAny,)
    example_oembed_response = {
        "version": "1.0",
        "provider_name": "DocumentCloud",
        "provider_url": "https://www.documentcloud.org",
        "cache_age": 300,
        "title": "the-mueller-report",
        "width": 800,
        "height": 1035,
        "html": """<iframe src="https://embed.documentcloud.org/documents/25524482-the-mueller-report/?embed=1" title="the-mueller-report (Hosted by DocumentCloud)" width="800" height="1035" style="border: 1px solid #aaa; width: 100%; height: 800px; height: calc(100vh - 100px);" sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-popups-to-escape-sandbox"></iframe>""", #pylint:disable=line-too-long
        "type": "rich",
    }

    @extend_schema(
        summary="oembed_retrieve",
        description="Retrieve an oEmbed response for embedding a document, page, or project.", #pylint:disable=line-too-long
        parameters=[
            OpenApiParameter(
                name="url",
                description="The URL of the resource to be embedded.",
                required=True,
                type=str,
                location=OpenApiParameter.QUERY,
            ),
            OpenApiParameter(
                name="maxwidth",
                description="Maximum width of the embedded resource (optional).",
                required=False,
                type=int,
                location=OpenApiParameter.QUERY,
            ),
            OpenApiParameter(
                name="maxheight",
                description="Maximum height of the embedded resource (optional).",
                required=False,
                type=int,
                location=OpenApiParameter.QUERY,
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="Successful response with an oEmbed payload.",
                response={
                    "type": "object",
                    "properties": {
                        "version": {"type": "string"},
                        "provider_name": {"type": "string"},
                        "provider_url": {"type": "string"},
                        "cache_age": {"type": "integer"},
                        "title": {"type": "string"},
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                        "html": {"type": "string"},
                        "type": {"type": "string"},
                    },
                },
                examples=[
                    OpenApiExample(
                        "oEmbed Response Example",
                        description="An example oEmbed response for the Mueller Report.", #pylint:disable=line-too-long
                        value=example_oembed_response,
                    ),
                ],
            ),
            400: OpenApiResponse(
                description="Bad request, missing or invalid parameters."
            ),
            404: OpenApiResponse(description="Requested resource not found."),
        },
    )
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
