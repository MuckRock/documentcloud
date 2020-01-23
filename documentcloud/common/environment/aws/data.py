# Standard Library
import json


def get_http_data(request):
    """Extract data from an HTTP request."""
    return json.loads(request["body"])


def get_pubsub_data(data):
    """Extract data from a pubsub request."""
    return json.loads(data["Records"][0]["Sns"]["Message"])


def encode_pubsub_data(data):
    """Encode data into the proper format for a pubsub request."""
    return json.dumps(data).encode("utf8")


def encode_response(data):
    """Encodes response into the proper format for an HTTP function."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(data),
    }
