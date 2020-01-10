# Third Party
import environ


env = environ.Env()

# Common environment variables
PROCESSING_TOKEN = env.str("PROCESSING_TOKEN")

AUTHORIZATION = "Authorization"


def processing_auth(func):
    """Authenticate a function by ensuring the processing token matches."""

    def authenticate_token(*args, **kwargs):
        event = args[0]
        headers = event["headers"]

        if headers.get(AUTHORIZATION) != f"processing-token {PROCESSING_TOKEN}":
            raise Exception("Authentication Failed.")

        # If all passes, auth succeeded
        return func(*args, **kwargs)

    return authenticate_token
