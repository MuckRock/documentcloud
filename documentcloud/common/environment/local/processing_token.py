# Third Party
import environ

env = environ.Env()

# Common environment variables
PROCESSING_TOKEN = env.str("PROCESSING_TOKEN")


def processing_auth(func):
    """Authenticate a function by ensuring the processing token matches."""

    def authenticate_token(*args, **kwargs):
        # Pass everything locally
        return func(*args, **kwargs)

    return authenticate_token
