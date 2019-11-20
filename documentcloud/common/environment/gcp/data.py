# Standard Library
import base64
import json

# XXX specialize to this environment


def get_http_data(request):
    """Extract data from an HTTP request that works across environments."""
    if hasattr(request, "get_json"):
        # Object is a request object
        return request.get_json()
    elif "body" in request:
        # Object is an AWS LambdaContext object
        return json.loads(request["body"])
    else:
        # Object is plain JSON
        return request


def get_pubsub_data(data):
    """Extract data from a pubsub request that works across environments."""
    if "Records" in data:
        return json.loads(data["Records"][0]["Sns"]["Message"])
    else:
        return json.loads(base64.b64decode(data["data"]).decode("utf-8"))
