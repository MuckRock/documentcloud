# Standard Library
import base64
import json


def get_http_data(request):
    """Extract data from an HTTP request."""
    return request.get_json()


def get_pubsub_data(data):
    """Extract data from a pubsub request."""
    return json.loads(base64.b64decode(data["data"]).decode("utf-8"))


def encode_pubsub_data(data):
    """Encode data into the proper format for a pubsub request."""
    return json.dumps(data).encode("utf8")


def encode_response(data):
    """Encodes response into the proper format for an HTTP function."""
    return data
