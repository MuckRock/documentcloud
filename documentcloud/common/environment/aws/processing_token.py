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

        def auth_failed():
            raise Exception("Authentication Failed.")

        if AUTHORIZATION in headers and headers[AUTHORIZATION] is not None:
            auth = headers[AUTHORIZATION]
            parts = auth.split(" ")

            # Authorization token is of form:
            # f"processing-token: {PROCESSING_TOKEN}"
            if len(parts) != 2:
                auth_failed()
            if parts[0] != "processing-token":
                auth_failed()
            if parts[1] != PROCESSING_TOKEN:
                auth_failed()
        else:
            auth_failed()

        # If all passes, auth succeeded
        return func(*args, **kwargs)

    return authenticate_token
